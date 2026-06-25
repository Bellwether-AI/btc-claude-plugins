<#
.SYNOPSIS
    PFX chain validation for Azure App Service BYOC rollouts (Windows / cross-platform PowerShell).

.DESCRIPTION
    Validates an Azure App Service-bound PFX certificate before upload, with three checks:
      1. PFX can be parsed (correct password, valid format)
      2. Intermediate chain is present (NOT a leaf-only PFX — the silent failure mode
         that causes TLS handshake breaks for clients without cached intermediates)
      3. Subject/SAN covers the expected hostname suffix (optional)

    PowerShell port of check_pfx.sh. Uses .NET's native X509Certificate2Collection — no
    dependency on openssl on the workstation. Works on Windows PowerShell 5.1+ and
    PowerShell 7+ (macOS, Linux, Windows).

.PARAMETER PfxPath
    Absolute path to the PFX file.

.PARAMETER HostnameSuffix
    Optional. If provided, the script also verifies the leaf cert's SAN covers
    hostnames under this suffix (e.g. "example.com").

.NOTES
    The PFX password MUST be passed via the PFX_PWD environment variable, not as
    a parameter. This keeps it out of PowerShell command history and process listings.

    Set with:
        $env:PFX_PWD = '<password>'

.EXAMPLE
    $env:PFX_PWD = '<password>'
    pwsh ./check_pfx.ps1 'C:\path\to\cert.pfx' 'example.com'

.OUTPUTS
    Exit code:
        0 — PFX is good (parses, in validity window, full chain present)
        1 — PFX is missing the intermediate chain (leaf-only)
        2 — PFX couldn't be parsed (wrong password? corrupted?)
        3 — Other validation failure (expired, SAN mismatch with the operator-provided suffix)
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true, Position=0)]
    [string]$PfxPath,

    [Parameter(Position=1)]
    [string]$HostnameSuffix
)

$ErrorActionPreference = 'Stop'

# --- Input validation -----------------------------------------------------

if (-not $env:PFX_PWD) {
    Write-Host "ERROR: PFX_PWD environment variable not set." -ForegroundColor Red
    Write-Host ""
    Write-Host "Set it first (in PowerShell):"
    Write-Host "    `$env:PFX_PWD = '<password>'"
    Write-Host ""
    Write-Host "The password MUST come from the PFX_PWD env var to avoid leaking it"
    Write-Host "into shell history or being visible in process listings."
    exit 2
}

if (-not (Test-Path $PfxPath -PathType Leaf)) {
    Write-Host "ERROR: PFX file not found at: $PfxPath" -ForegroundColor Red
    exit 2
}

# --- Load the PFX ---------------------------------------------------------

$collection = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2Collection

# DefaultKeySet (= 0) works on Windows, macOS, and Linux. EphemeralKeySet is
# Windows-only — on macOS .NET it throws "This platform does not support
# loading with EphemeralKeySet." DefaultKeySet writes the key material to a
# temp file on non-Windows platforms, which is fine since this script only
# inspects metadata and doesn't sign anything.
try {
    $collection.Import(
        $PfxPath,
        $env:PFX_PWD,
        [System.Security.Cryptography.X509Certificates.X509KeyStorageFlags]::DefaultKeySet
    )
} catch {
    Write-Host "ERROR: Could not parse PFX. Likely wrong password or unsupported encoding." -ForegroundColor Red
    Write-Host "       .NET says: $($_.Exception.Message)"
    exit 2
}

$certCount = $collection.Count
Write-Host "Certificates extracted from PFX: $certCount"

if ($certCount -eq 0) {
    Write-Host "ERROR: PFX parsed but no certificates extracted." -ForegroundColor Red
    exit 2
}

# --- Identify the leaf cert -----------------------------------------------
# The leaf is the cert whose subject is not the issuer of any other cert in the
# bundle. PFX export typically puts the leaf first, but we're being defensive.

$leaf = $null
foreach ($cert in $collection) {
    $isIssuerOfOthers = $false
    foreach ($other in $collection) {
        if ($other.Thumbprint -ne $cert.Thumbprint -and $other.Issuer -eq $cert.Subject) {
            $isIssuerOfOthers = $true
            break
        }
    }
    if (-not $isIssuerOfOthers) {
        $leaf = $cert
        break
    }
}
if (-not $leaf) { $leaf = $collection[0] }

Write-Host ""
Write-Host "=== LEAF CERT ==="
Write-Host "Subject:    $($leaf.Subject)"
Write-Host "Issuer:     $($leaf.Issuer)"
Write-Host "NotBefore:  $($leaf.NotBefore.ToUniversalTime().ToString('u'))"
Write-Host "NotAfter:   $($leaf.NotAfter.ToUniversalTime().ToString('u'))"
Write-Host "Thumbprint: $($leaf.Thumbprint)"
Write-Host "Serial:     $($leaf.SerialNumber)"

# SAN extraction (OID 2.5.29.17)
# The Format() output differs across .NET implementations:
#   Windows:  "DNS Name=*.example.com\nDNS Name=example.com"
#   macOS:    "DNS:*.example.com, DNS:example.com"
#   Linux:    "DNS:*.example.com, DNS:example.com"   (typically)
# So we match either "DNS Name=value", "DNS=value", or "DNS:value", on any line,
# and split on either commas or newlines first.
$sanExt = $null
foreach ($e in $leaf.Extensions) {
    if ($e.Oid.Value -eq '2.5.29.17') { $sanExt = $e; break }
}
$sanEntries = @()
if ($sanExt) {
    $sanText = $sanExt.Format($false)
    foreach ($chunk in ($sanText -split '[,\r\n]+')) {
        $chunk = $chunk.Trim()
        if ($chunk -match '^\s*DNS(\s+Name)?\s*[:=]\s*(.+?)\s*$') {
            $sanEntries += $matches[2]
        }
    }
}
Write-Host "SAN entries:"
if ($sanEntries.Count -gt 0) {
    foreach ($s in $sanEntries) { Write-Host "  $s" }
} else {
    Write-Host "  (none — leaf cert has no SAN extension)"
}

# --- Validity window check ------------------------------------------------

$daysLeft = [int]($leaf.NotAfter.ToUniversalTime() - [datetime]::UtcNow).TotalDays
Write-Host "Days until expiry: $daysLeft"

if ($daysLeft -lt 0) {
    Write-Host "ERROR: Cert is already expired (notAfter: $($leaf.NotAfter))." -ForegroundColor Red
    exit 3
} elseif ($daysLeft -lt 14) {
    Write-Host "WARNING: Cert expires in under 2 weeks. Confirm intent before rolling out." -ForegroundColor Yellow
}

# --- Chain check ----------------------------------------------------------

Write-Host ""
Write-Host "=== CHAIN CHECK ==="
if ($certCount -lt 2) {
    Write-Host "FAIL: Only 1 certificate in PFX. Intermediate chain is NOT bundled." -ForegroundColor Red
    Write-Host "      App Service will accept this upload silently, but clients with clean"
    Write-Host "      trust stores (curl on minimal containers, Go's default client, mobile"
    Write-Host "      apps using bundled trust stores) will fail TLS verification."
    Write-Host ""
    Write-Host "      Re-export the PFX with the full chain (leaf + intermediates + root)."
    Write-Host "      OpenSSL example:"
    Write-Host "          openssl pkcs12 -export -out new.pfx ``"
    Write-Host "                         -inkey key.pem -in leaf.pem -certfile chain.pem"
    exit 1
}

Write-Host "Chain has $certCount certs total. Walking the chain..."

# Order: leaf first, then walk by issuer-matches-next-subject
$ordered = New-Object System.Collections.Generic.List[System.Security.Cryptography.X509Certificates.X509Certificate2]
$ordered.Add($leaf) | Out-Null
$remaining = New-Object System.Collections.Generic.List[System.Security.Cryptography.X509Certificates.X509Certificate2]
foreach ($cert in $collection) {
    if ($cert.Thumbprint -ne $leaf.Thumbprint) { $remaining.Add($cert) | Out-Null }
}

while ($remaining.Count -gt 0) {
    $lookingFor = $ordered[$ordered.Count - 1].Issuer
    $next = $null
    foreach ($candidate in $remaining) {
        if ($candidate.Subject -eq $lookingFor) {
            $next = $candidate
            break
        }
    }
    if ($null -eq $next) {
        # Couldn't continue the chain — append whatever's left in arbitrary order
        # and flag below
        foreach ($r in $remaining) { $ordered.Add($r) | Out-Null }
        break
    }
    $ordered.Add($next) | Out-Null
    $remaining.Remove($next) | Out-Null
}

$prevIssuer = ""
for ($i = 0; $i -lt $ordered.Count; $i++) {
    $cert = $ordered[$i]
    $idxStr = "{0:D2}" -f $i
    Write-Host "  [$idxStr] subject: $($cert.Subject)"
    Write-Host "       issuer:  $($cert.Issuer)"
    Write-Host "       sha1:    $($cert.Thumbprint)"

    if ($prevIssuer) {
        if ($prevIssuer -eq $cert.Subject) {
            Write-Host "       OK - chains from cert $($i - 1)"
        } else {
            Write-Host "       WARN - this cert's subject does not match the previous cert's issuer."
            Write-Host "              previous issuer was: $prevIssuer"
            Write-Host "              this subject is:     $($cert.Subject)"
            Write-Host "              Chain may be broken or out of order — investigate before uploading."
        }
    }
    $prevIssuer = $cert.Issuer
}

# Self-signed root check
$last = $ordered[$ordered.Count - 1]
if ($last.Subject -eq $last.Issuer) {
    Write-Host "  OK - chain terminates in a self-signed root."
} else {
    Write-Host "  WARN - last cert is not self-signed. Root may be assumed from client trust store."
    Write-Host "         Usually fine, but worth noting."
}

# --- Hostname coverage check (optional) -----------------------------------

if ($HostnameSuffix) {
    Write-Host ""
    Write-Host "=== HOSTNAME COVERAGE CHECK ==="
    Write-Host "Checking SAN against hostname suffix: $HostnameSuffix"

    # Anchor with a literal leading dot so 'example.com' doesn't match 'notexample.com'.
    $matchedWildcard = $false
    $matchedAnySuffix = $false
    foreach ($entry in $sanEntries) {
        if ($entry -eq "*.$HostnameSuffix") { $matchedWildcard = $true }
        if ($entry.EndsWith(".$HostnameSuffix")) { $matchedAnySuffix = $true }
    }

    if ($matchedWildcard) {
        Write-Host "  OK - wildcard *.$HostnameSuffix present - covers any single-label subdomain."
    } elseif ($matchedAnySuffix) {
        Write-Host "  OK - at least one SAN ends in .$HostnameSuffix (not wildcard - verify per-hostname coverage)."
    } else {
        Write-Host "  WARN - no SAN matches suffix .$HostnameSuffix. This PFX may not cover the target hostnames." -ForegroundColor Yellow
        exit 3
    }
}

Write-Host ""
Write-Host "=== RESULT: PFX validation PASSED ==="
exit 0
