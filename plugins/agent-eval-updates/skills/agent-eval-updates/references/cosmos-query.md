# CosmosDB query reference

Everything you need to pull and interpret BTC agent evaluation data. The `query_evals.py` tool at the project root already handles auth, pagination, and file output — you rarely need to talk to CosmosDB directly.

## CosmosDB environment

| Field | Value |
|-------|-------|
| Endpoint | `https://btc-ai-cosmosdb.documents.azure.com:443/` |
| Database | `agents` |
| Production container | `agent-output` (where real traffic + human ratings land) |
| Test container | `agent-output-test` (where local-dev runs write) |
| Auth | `DefaultAzureCredential` (requires active `az login`) |
| Subscription | `BTC - Sponsored - 6000 annual` (as of 2026-04) |

If queries return 403, the user may need to `az account set --subscription <id>` before proceeding.

## query_evals.py usage

```bash
cd /Users/mattlax/nonedrive/projects/btc_agent_evals

# List every agentType in the container (with rated-item counts)
uv run python query_evals.py --list-agents

# Pull all rated items for an agent since a date
uv run python query_evals.py -a ticket_prioritizer --since 2026-03-13T00:00:00Z

# Shorthand: last 5 days
uv run python query_evals.py -a ticket_reviewer --since 5d

# Count only (no file writes)
uv run python query_evals.py -a ticket_prioritizer --since 5d --count

# Query the test container instead
uv run python query_evals.py -a ticket_prioritizer --since 2d --container agent-output-test
```

### Output files

Each run writes two files into `eval_data/`:

- `<agent>_evals_<timestamp>.json` — full CosmosDB documents, grouped under `items: [...]` with a top-level `metadata` block.
- `<agent>_summary_<timestamp>.json` — extracted key fields per item, bucketed by star rating in `by_rating: {1: [...], 2: [...], ...}`.

The summary file is what you usually read first. It contains ticket_id, company, original_priority, rating, evaluator, eval_comment, llm_decision, llm_actionability, llm_summary, execution_ms per item — enough to triage most patterns without opening the full docs.

Open the full `_evals_*.json` when you need `input.rawEvent` (to replay a ticket via webhook in Phase 7), `llmRequest`/`llmResponse` (to inspect exactly what the LLM saw), or `structuredResult.findings` (to see per-check scores on ticket_reviewer).

## Document schema (agent output)

```json
{
  "id": "<uuid>",
  "agentType": "ticket_prioritizer",
  "assistantName": "service_desk_lead",
  "status": { "state": "completed" },

  "content": {
    "rating": 1-5,
    "ratingDetails": {
      "rating": 1-5,
      "userId": "<uuid>",
      "username": "email@domain.com",
      "comment": "Human feedback",
      "timestamp": "ISO8601"
    }
  },

  "input": {
    "userMessage": "<full message to LLM>",
    "context": {
      "ticket": { /* ConnectWise ticket at time of run */ },
      "action": "updated",
      "enrichedTicket": { "TimeEntries": [...], "TicketNotes": [...] }
    },
    "metadata": { "ticketId": "...", "memberId": "...", "companyId": "...", ... },
    "rawEvent": { /* original webhook payload */ }
  },

  "llmRequest":  { "messages": [...], "responseFormat": {...}, "tools": [] },
  "llmResponse": { "content": {...}, "rawResponse": {...}, "usage": { "totalTokens": N } },

  "structuredResult": {
    "type": "ticket_prioritizer",        /* or ticket_reviewer, etc. */
    "schemaVersion": "2.0.0",
    "itemId": "<ticket id>",
    "itemType": "ticket",
    "summary": "...",
    "actionability": 0-3,
    "decision": "priority_1|priority_2|priority_3|no_change|approved|reject|supervisor|evaluate",
    "confidence": 0.0-1.0,
    "findings": [ /* per-check results */ ]
  },

  "timing": { "startedAt": "...", "completedAt": "...", "durationMs": N },
  "_ts":  1234567890    /* CosmosDB timestamp — WHEN THE AGENT RAN */
}
```

## Two timestamps — know the difference

- `_ts` — unix seconds for when the document was written (the agent's execution time). Used by the pre-fix artifact filter.
- `content.ratingDetails.timestamp` — ISO8601 for when the human rated the item. Can be much later than `_ts`.

The pre-fix artifact filter compares `_ts` against `mergedAt` of the previous round's fix PRs, NOT the rating timestamp. An item rated on 2026-03-20 could easily have run on 2026-03-13 — if that run predates the PR #70 deploy, it's a pre-fix artifact even though the rating is recent.

## Rating interpretation

| Rating | Meaning | Focus? |
|--------|---------|--------|
| 1 | Complete failure — wrong output, missed critical info | Yes |
| 2 | Failure with some correct elements | Yes |
| 3 | Failure with some correct elements | Yes |
| 4 | Correct but needs adjustment (reasoning, nuance) — OFTEN a feature request, not a prompt bug | Read comment carefully |
| 5 | Complete success | Only as regression reference |

Look at 4-star comments specifically — the user pattern is "correct decision, but also [unrelated ask]". That "unrelated ask" is usually a feature request for BTC-Python-Agents (skip logic, different routing, new enrichment), not a prompt fix.

## Direct queries (only if query_evals.py doesn't cover it)

For anything `query_evals.py` can't do (e.g., checking specific tickets in the test container), use the Python SDK directly:

```python
import os
os.environ['AZURE_COSMOS_DISABLE_ORJSON'] = '1'
import logging
logging.getLogger('azure').setLevel(logging.WARNING)

from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential
from datetime import datetime, timezone

client = CosmosClient(
    'https://btc-ai-cosmosdb.documents.azure.com:443/',
    credential=DefaultAzureCredential(logging_enable=False),
)
container = client.get_database_client('agents').get_container_client('agent-output-test')

cutoff = int(datetime(2026, 4, 17, 17, 18, 0, tzinfo=timezone.utc).timestamp())
query = f"""
SELECT c.input.context.ticket.id AS ticket_id,
       c.agentType,
       c.structuredResult.decision,
       c.structuredResult.actionability,
       c._ts
FROM c
WHERE c._ts >= {cutoff}
ORDER BY c._ts DESC
"""
for item in container.query_items(query=query, enable_cross_partition_query=True):
    ...
```

Notes:
- `AZURE_COSMOS_DISABLE_ORJSON=1` is required (the BTC-Python-Agents project sets this due to a compat issue).
- `DefaultAzureCredential(logging_enable=False)` + `logging.getLogger('azure').setLevel(WARNING)` cuts the wall of HTTP log output.
- `enable_cross_partition_query=True` is required for any aggregate or multi-partition query.
