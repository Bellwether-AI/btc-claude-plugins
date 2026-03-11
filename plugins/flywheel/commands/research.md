---
description: Research and analyze a topic, producing a structured summary
---
# Flywheel: Research & Analysis

Gather information from multiple sources, synthesize findings, and write a structured summary to the work item's `## Artifacts` section.

## Environment

```bash
FLYWHEEL_PATH="$HOME/.flywheel"
```

## Process

### 1. Load the Work Item

Check for a prompt file first (launched from dashboard):

1. Use `Glob(pattern=".flywheel-prompt-*.txt")` to find prompt files in the current directory
2. If found, use `Read` to read the prompt file contents

Or find the active work item:

1. Use `Grep(pattern="^- status: planned", path="$FLYWHEEL_PATH/work/")` to find work items
2. Use `Read` to read the matching work item file

Extract:
- The research question or topic from the description
- Any specific sources or constraints mentioned
- What format the output should take

### 2. Plan Research Strategy

Based on the work item, determine which sources to consult:

| Source | Tool | When to Use |
|--------|------|-------------|
| Web | `WebSearch`, `WebFetch` | General research, current events, documentation |
| Email (Gmail) | `mcp__claude_ai_Gmail__gmail_search_messages` | Finding past conversations, decisions |
| Email (Outlook) | `mcp__claude_ai_ms365__outlook_email_search` | Finding past conversations, decisions |
| Calendar | `mcp__claude_ai_ms365__outlook_calendar_search` | Meeting history, scheduling context |
| Teams | `mcp__claude_ai_ms365__chat_message_search` | Team discussions, decisions |
| SharePoint | `mcp__claude_ai_ms365__sharepoint_search` | Company documents, wikis |
| Meeting transcripts | `mcp__claude_ai_Fireflies__fireflies_search` | Meeting discussions, action items |
| Local files | `Grep`, `Read` | Codebase, local docs |
| Browser | `mcp__claude-in-chrome__*` | Pages requiring interaction |

### 3. Execute Research

For each source in the strategy:

1. **Search** — Query the source with relevant terms
2. **Read** — Fetch full content of relevant results
3. **Extract** — Pull out key findings, quotes, data points
4. **Log** — Update execution log with what was found

Keep notes on:
- Source and date for each finding
- Direct quotes or data points (with attribution)
- Conflicting information across sources
- Gaps where information is missing

### 4. Synthesize Findings

Organize findings into a structured summary:

```markdown
### Research: [Topic]

**Question:** [The research question]

**Sources Consulted:**
- [Source 1] — [what was found]
- [Source 2] — [what was found]

**Key Findings:**
1. [Finding with supporting evidence]
2. [Finding with supporting evidence]
3. [Finding with supporting evidence]

**Recommendations:**
- [Action item based on findings]
- [Action item based on findings]

**Open Questions:**
- [Things that couldn't be determined]
```

### 5. Write Artifacts

Write the research summary to the work item's `## Artifacts` section.

If the work item doesn't have an `## Artifacts` section, add one before `## Execution Log`:
```
Edit(file_path="$WORK_ITEM_PATH",
     old_string="## Execution Log",
     new_string="## Artifacts\n\n[Research summary here]\n\n## Execution Log")
```

If it already has `## Artifacts`, append to it.

### 6. Update Work Item

- Mark relevant success criteria as complete `[x]`
- Update execution log with research completion
- If all criteria met, transition to `review` status

### 7. Report

```markdown
## Research Complete

### Sources Consulted
- [List of sources searched]

### Key Findings
- [Top 3-5 findings]

### Artifacts Written
- Research summary written to work item `## Artifacts` section

### Next Steps
Review the findings in the work item and run `/flywheel:done` when satisfied.
```

## Tips

- **Cast a wide net first** — search broadly, then drill into specific findings
- **Cross-reference** — verify claims across multiple sources
- **Note recency** — prefer recent information over older sources
- **Be honest about gaps** — explicitly note what you couldn't find
- **Attribute everything** — include source for every finding
