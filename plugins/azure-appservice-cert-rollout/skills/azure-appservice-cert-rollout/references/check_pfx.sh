#!/usr/bin/env bash
# PFX chain validation for Azure App Service BYOC rollouts.
#
# Usage:
#   PFX_PWD='<password>' bash check_pfx.sh <pfx-path> [expected-hostname-suffix]
#
# The PFX password MUST be passed via the PFX_PWD environment variable, not as
# a positional argument. This keeps it out of shell history and `ps` output.
# Internally we use `openssl ... -passin env:PFX_PWD` so it never lands on argv.
#
# Exit codes:
#   0 — PFX is good (parses, in validity window, full chain present)
#   1 — PFX is missing the intermediate chain (only the leaf inside) — chain-less upload risk
#   2 — PFX couldn't be parsed (wrong password? corrupted file?)
#   3 — Other validation failure (expired, SAN mismatch with the operator-provided suffix, etc.)
#
# Why: az webapp config ssl upload will silently accept a leaf-only PFX with no
# intermediates. The resulting binding works in most browsers (which cache common
# intermediates) but fails TLS handshakes from clients with clean trust stores.
# There's no portal warning. This script is the only defense before upload.
#
# Portability: targets macOS (BSD) and Linux (GNU) without GNU coreutils. Uses
# awk for per-cert splitting (avoids GNU-only csplit -z / -b / "{*}" flags) and
# detects BSD vs GNU date for expiry parsing.

set -euo pipefail

PFX="${1:-}"
HOSTNAME_SUFFIX="${2:-}"

if [[ -z "${PFX_PWD:-}" || -z "$PFX" ]]; then
  echo "Usage: PFX_PWD='<password>' bash check_pfx.sh <pfx-path> [hostname-suffix]" >&2
  echo "" >&2
  echo "The PFX password MUST come from the PFX_PWD env var to avoid leaking it" >&2
  echo "into shell history or being visible in 'ps'." >&2
  exit 2
fi

if [[ ! -f "$PFX" ]]; then
  echo "ERROR: PFX file not found at: $PFX" >&2
  exit 2
fi

TMP=$(mktemp -d)
trap "rm -rf $TMP" EXIT

# Extract certs only (no keys). openssl reads the password from env:PFX_PWD so
# it never appears on argv. Retry with -legacy for older Windows/IIS PFXes.
if ! openssl pkcs12 -in "$PFX" -nokeys -passin env:PFX_PWD -out "$TMP/chain.pem" 2>"$TMP/err"; then
  if ! openssl pkcs12 -in "$PFX" -nokeys -passin env:PFX_PWD -legacy -out "$TMP/chain.pem" 2>"$TMP/err"; then
    echo "ERROR: Could not parse PFX. Likely wrong password or unsupported encoding."
    echo "       openssl says:"
    sed 's/^/         /' "$TMP/err"
    exit 2
  fi
fi

# Portable per-cert splitter. awk emits each PEM block to its own file.
# Numbered cert-00.pem, cert-01.pem, ... so the leaf is always cert-00.
awk -v tmp="$TMP" '
  /-----BEGIN CERTIFICATE-----/ {
    n++
    out = sprintf("%s/cert-%02d.pem", tmp, n - 1)
  }
  n > 0 { print > out }
' "$TMP/chain.pem"

CERT_COUNT=$(find "$TMP" -name 'cert-*.pem' -type f | wc -l | tr -d ' ')
echo "Certificates extracted from PFX: $CERT_COUNT"

if [[ "$CERT_COUNT" -eq 0 ]]; then
  echo "ERROR: PFX parsed but no certificates extracted. Corrupted file or unexpected format."
  exit 2
fi

LEAF="$TMP/cert-00.pem"

echo ""
echo "=== LEAF CERT ==="
openssl x509 -in "$LEAF" -noout -subject -issuer -dates -fingerprint -sha1 -serial

SAN=$(openssl x509 -in "$LEAF" -noout -ext subjectAltName 2>/dev/null \
        | grep -oE 'DNS:[^,]+' | sed 's/DNS://g' | tr -d ' ' || true)
echo "SAN entries:"
if [[ -n "$SAN" ]]; then
  echo "$SAN" | sed 's/^/  /'
else
  echo "  (none — leaf cert has no SAN extension)"
fi

# Expiry. Try BSD date first (macOS), fall back to GNU date (Linux).
NOT_AFTER=$(openssl x509 -in "$LEAF" -noout -enddate | sed 's/notAfter=//')
NOT_AFTER_EPOCH=$(date -j -f "%b %e %T %Y %Z" "$NOT_AFTER" "+%s" 2>/dev/null \
               || date -d "$NOT_AFTER" "+%s" 2>/dev/null \
               || echo 0)
NOW_EPOCH=$(date +%s)
DAYS_LEFT=$(( (NOT_AFTER_EPOCH - NOW_EPOCH) / 86400 ))
echo "Days until expiry: $DAYS_LEFT"

if [[ "$NOT_AFTER_EPOCH" -eq 0 ]]; then
  echo "WARNING: Could not parse the cert's notAfter date for validity check."
elif [[ "$DAYS_LEFT" -lt 0 ]]; then
  echo "ERROR: Cert is already expired (notAfter: $NOT_AFTER)."
  exit 3
elif [[ "$DAYS_LEFT" -lt 14 ]]; then
  echo "WARNING: Cert expires in under 2 weeks. Confirm intent before rolling out."
fi

# Chain check — this is the whole point of the script.
echo ""
echo "=== CHAIN CHECK ==="
if [[ "$CERT_COUNT" -lt 2 ]]; then
  echo "FAIL: Only 1 certificate in PFX. Intermediate chain is NOT bundled."
  echo "      App Service will accept this upload silently, but clients with clean"
  echo "      trust stores (curl on minimal containers, Go's default client, mobile"
  echo "      apps using bundled trust stores) will fail TLS verification."
  echo ""
  echo "      Re-export the PFX with the full chain (leaf + intermediates + root)."
  echo "      OpenSSL example:"
  echo "          openssl pkcs12 -export -out new.pfx \\"
  echo "                         -inkey key.pem -in leaf.pem -certfile chain.pem"
  exit 1
fi

echo "Chain has $CERT_COUNT certs total. Walking the chain..."
PREV_ISSUER=""
for i in $(find "$TMP" -name 'cert-*.pem' -type f | sort); do
  IDX=$(basename "$i" | sed 's/cert-//;s/.pem//')
  SUBJ=$(openssl x509 -in "$i" -noout -subject 2>/dev/null | sed 's/subject=//')
  ISSUER=$(openssl x509 -in "$i" -noout -issuer 2>/dev/null | sed 's/issuer=//')
  FP=$(openssl x509 -in "$i" -noout -fingerprint -sha1 2>/dev/null | sed 's/^.*=//')
  echo "  [$IDX] subject: $SUBJ"
  echo "       issuer:  $ISSUER"
  echo "       sha1:    $FP"

  if [[ -n "$PREV_ISSUER" ]]; then
    if [[ "$PREV_ISSUER" == "$SUBJ" ]]; then
      echo "       ✓ chains from cert $((10#$IDX - 1))"
    else
      echo "       ⚠ this cert's subject does not match the previous cert's issuer."
      echo "         previous issuer was: $PREV_ISSUER"
      echo "         this subject is:     $SUBJ"
      echo "         Chain may be broken or out of order — investigate before uploading."
    fi
  fi
  PREV_ISSUER="$ISSUER"
done

# Self-signed root check.
LAST=$(find "$TMP" -name 'cert-*.pem' -type f | sort | tail -1)
LAST_SUBJ=$(openssl x509 -in "$LAST" -noout -subject | sed 's/subject=//')
LAST_ISSUER=$(openssl x509 -in "$LAST" -noout -issuer | sed 's/issuer=//')
if [[ "$LAST_SUBJ" == "$LAST_ISSUER" ]]; then
  echo "  ✓ chain terminates in a self-signed root."
else
  echo "  ⚠ last cert is not self-signed. Root may be assumed from client trust store."
  echo "    Usually fine, but worth noting."
fi

# Optional hostname coverage check against operator-provided suffix.
if [[ -n "$HOSTNAME_SUFFIX" ]]; then
  echo ""
  echo "=== HOSTNAME COVERAGE CHECK ==="
  echo "Checking SAN against hostname suffix: $HOSTNAME_SUFFIX"
  ESC_SUFFIX="${HOSTNAME_SUFFIX//./\\.}"
  if echo "$SAN" | grep -qE "(^|\s)\*\.${ESC_SUFFIX}\b"; then
    echo "  ✓ wildcard *.${HOSTNAME_SUFFIX} present — covers any single-label subdomain."
  elif echo "$SAN" | grep -qE "${ESC_SUFFIX}\$"; then
    echo "  ✓ at least one SAN ends in ${HOSTNAME_SUFFIX} (not wildcard — verify per-hostname coverage)."
  else
    echo "  ⚠ no SAN matches suffix ${HOSTNAME_SUFFIX}. This PFX may not cover the target hostnames."
    exit 3
  fi
fi

echo ""
echo "=== RESULT: PFX validation PASSED ==="
exit 0
