# Local testing reference

How to exercise edited prompts + agent code against real ServiceBus traffic and directed webhook replays — without touching the production blob.

## Core idea: scratch prompt overlay

Each per-agent worktree holds only that agent's edited prompt file(s). For local testing with ONE running `func` instance covering multiple agents, we need a single directory tree with every agent's edited file layered on top of origin/main's full prompts tree. That's the "scratch overlay":

```bash
cd /Users/mattlax/nonedrive/projects/btc_agent_evals
mkdir -p .worktrees/test-prompts

# 1. Baseline: origin/main prompts
cd BTCAgentPrompts
git archive origin/main prompts/ | tar -x -C ../.worktrees/test-prompts/

# 2. Overlay each worktree's edits
cp ../.worktrees/btc-agent-prompts-prioritizer/prompts/ServiceDeskLeadAssistant/TicketPrioritizerAgent/TicketPrioritizerAgent.md \
   ../.worktrees/test-prompts/prompts/ServiceDeskLeadAssistant/TicketPrioritizerAgent/TicketPrioritizerAgent.md
cp ../.worktrees/btc-agent-prompts-reviewer/prompts/SupportManagerAssistant/TicketReviewerAgent/TicketReviewerAgent.md \
   ../.worktrees/test-prompts/prompts/SupportManagerAssistant/TicketReviewerAgent/TicketReviewerAgent.md
```

Point `LOCAL_PROMPT_BASE_PATH` at the scratch dir in `BTC-Python-Agents/local.settings.json` (use absolute path):

```json
"LOCAL_PROMPT_BASE_PATH": "/Users/mattlax/nonedrive/projects/btc_agent_evals/.worktrees/test-prompts/prompts",
"USE_BLOB_STORAGE_PROMPTS": "false"
```

`local.settings.json` is gitignored so editing it is safe and leaves no PR dirtyness.

**Never upload to the production blob from a tuning session.** CI/CD deploys on merge — that's the authoritative path.

## Starting services

BTC-Python-Agents is a **Python** Azure Functions project. Do NOT set `DOTNET_ROOT` or use any .NET-specific tooling — those instructions come from the PolicyConductor project and do not apply here.

### Terminal 1: Azurite (nvm-based)

```bash
cd /Users/mattlax/nonedrive/projects/btc_agent_evals/BTC-Python-Agents
mkdir -p __azurite__
export NVM_DIR="$HOME/.nvm" && . "$NVM_DIR/nvm.sh"
nohup azurite --silent --location __azurite__ --debug __azurite__/debug.log > __azurite__/stdout.log 2>&1 &
```

Ports: 10000 (Blob), 10001 (Queue), 10002 (Table). Verify with `lsof -iTCP:10000 -sTCP:LISTEN`.

### Terminal 2: func

```bash
cd /Users/mattlax/nonedrive/projects/btc_agent_evals/BTC-Python-Agents
nohup uv run func start > ../func-start.log 2>&1 &
```

The `az login` session is used to pull KeyVault-referenced secrets in `local.settings.json` (CosmosDB keys, ConnectWise creds, OpenAI key, etc.). If startup fails with auth errors, check `az account show`.

### Verify scratch prompt loads

Grep the func log for `System prompt length`:

```bash
grep "System prompt length" /Users/mattlax/nonedrive/projects/btc_agent_evals/func-start.log | head -5
```

The character count should match your edited file's byte count (run `wc -c` on the scratch dir's copy). If it doesn't match, `LOCAL_PROMPT_BASE_PATH` is pointing somewhere else.

## ServiceBus subscriptions (automatic live traffic)

Relevant env vars in `local.settings.json`:

```
SERVICEBUS_SUB_TICKET_PRIORITIZER: ticket-prioritizer-testing
SERVICEBUS_SUB_TICKET_REVIEWER:    ticket-reviewer-testing
```

These testing subscriptions are topic siblings of the production ones — every real ConnectWise webhook event is mirrored to them. When func boots, it starts draining the backlog (may include hours or days of messages) and processing live events. This is the "15-minute soak" period.

## TICKET_*_RESOURCE_FILTER semantics

```
TICKET_PRIORITIZER_RESOURCE_FILTER: mlax
TICKET_REVIEWER_RESOURCE_FILTER:    mlax
```

These filters ONLY gate whether **automations** (CW priority changes, CW ticket rejections, internal-note writes) fire. The LLM evaluation runs, the CosmosDB write happens, and enrichment API calls happen regardless of the filter.

Implication: test webhook replays with `member_id != "mlax"` are safe — the agent will evaluate and write to CosmosDB but will NOT take any action in ConnectWise. Use `claude.test.round<N>` or similar for the test replay `member_id`.

## Webhook replay recipe

### CallbackObjectRecId routing

| Value | Routes to |
|-------|-----------|
| `19257` | ticket_prioritizer |
| `19259` or `19260` | ticket_reviewer |

(These come from ConnectWise Service Board webhook registration — confirm against the agent under test if in doubt.)

### Recipe: extract rawEvent, rewrite member_id, POST

```bash
# 1. Extract each failure ticket's original webhook from the eval JSON
uv run python - <<'PY'
import json
for tid in [1393194, 1392567, 1392418, 1394487]:
    for agent in ('ticket_prioritizer', 'ticket_reviewer'):
        # load most recent <agent>_evals_*.json, find the item with matching ticket_id,
        # write item['input']['rawEvent'] to /tmp/webhook_<tid>.json
        ...
PY

# 2. Rewrite member_id so automations don't fire on these historical tickets
uv run python - <<'PY'
import json
for tid in [...]:
    with open(f'/tmp/webhook_{tid}.json') as f: wh = json.load(f)
    wh['member_id'] = 'claude.test.round4'
    if 'entity' in wh and isinstance(wh['entity'], dict):
        wh['entity'].setdefault('_info', {})
        wh['entity']['_info']['updatedBy'] = 'claude.test.round4'
    with open(f'/tmp/webhook_{tid}.json', 'w') as f: json.dump(wh, f)
PY

# 3. POST to local webhook
for tid in 1393194 1392567 1392418 1394487; do
  curl -s -X POST http://localhost:7071/api/webhook \
    -H "Content-Type: application/json" \
    --data @/tmp/webhook_${tid}.json
  sleep 2
done
```

## Debounce timing

`DEBOUNCE_SECONDS` defaults to 120. Model:

1. Webhook hits `/api/webhook` → router identifies target agent and debounces via Redis.
2. Debounce upserts `(target, entity_id, member_id)` with `due_at = now + 120s`.
3. `DebounceWorker` timer fires every 2s and dispatches due tickets onto the target ServiceBus queue.
4. The agent's ServiceBus trigger then processes it.

Consequence: your manually-POSTed webhook won't execute for 2+ minutes. And if the ServiceBus backlog is large, the agent may further delay processing behind real traffic.

Override for E2E tests by setting `DEBOUNCE_SECONDS=0`, but don't do that for tuning validation — the debounce is part of production behavior and we want to exercise it.

## Skip-phrase + override detectors (Round 3 deterministic logic)

Some tickets carry phrases like "do not prioritize", "Override Review: approve", etc. in their notes or time entries — usually annotations added by evaluators from prior rounds. These trigger **pre-LLM** deterministic code paths that bypass the agent. Your test replay will be skipped cleanly; you'll see a log line like `⏭️ Skip phrase 'do not prioritize' found in ticket <id> notes — skipping prioritization`.

This isn't a bug; it's the intended deterministic behavior. Log it, note it in the evaluation report, and rely on real-traffic soak + other test tickets for validation.

## Watching logs + CosmosDB

Two parallel signals — tail the func log for behavior, query CosmosDB for outputs.

### Filtered log tail

```bash
tail -f func-start.log \
  | grep -E "(<tid1>|<tid2>|...).*(completed|failed|Skipping|decision|priority_|reject|approved|evaluate)|Traceback|Error processing"
```

Or use the `Monitor` tool for a persistent stream.

### Query agent-output-test for expected results

```python
import os; os.environ['AZURE_COSMOS_DISABLE_ORJSON'] = '1'
import logging; logging.getLogger('azure').setLevel(logging.WARNING)
from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential
from datetime import datetime, timezone

client = CosmosClient(
    'https://btc-ai-cosmosdb.documents.azure.com:443/',
    credential=DefaultAzureCredential(logging_enable=False),
)
c = client.get_database_client('agents').get_container_client('agent-output-test')

cutoff = int(datetime(YYYY,MM,DD,HH,MM,0, tzinfo=timezone.utc).timestamp())
target = [1393194, 1392567, 1392418, 1394487]
query = f"""
SELECT c.input.context.ticket.id AS tid, c.agentType,
       c.structuredResult.decision, c.structuredResult.actionability,
       c.structuredResult.summary, c._ts, c.input.metadata.memberId AS mid
FROM c
WHERE c.input.context.ticket.id IN ({','.join(str(t) for t in target)})
  AND c._ts >= {cutoff}
ORDER BY c._ts DESC
"""
for item in c.query_items(query=query, enable_cross_partition_query=True):
    ...
```

## Evaluation criteria

The user's primary success criterion for the soak is **no new false positives**. Specific test-ticket matches against evaluator-expected outcomes are secondary and may legitimately diverge because the ticket's current state has evolved since the original eval (files now restored, ticket now closed, status changed, etc.). The existing de-escalation rules correctly handle post-resolution tickets and should be respected.

## Cleanup (Phase 9)

At full wrap-up:

```bash
pkill -f "func start"
pkill -f azurite
# Follow up with kill -9 <pids> if stubborn

# Revert local.settings.json LOCAL_PROMPT_BASE_PATH to "../BTCAgentPrompts/prompts"

# Remove scratch + service dirs
rm -rf /Users/mattlax/nonedrive/projects/btc_agent_evals/.worktrees/test-prompts
rm -rf /Users/mattlax/nonedrive/projects/btc_agent_evals/BTC-Python-Agents/__azurite__
rm -f /Users/mattlax/nonedrive/projects/btc_agent_evals/func-start.log
```
