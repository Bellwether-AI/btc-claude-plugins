---
description: Draft text content like emails, documents, and proposals
---
# Flywheel: Writing & Drafting

Draft text content (emails, documents, proposals, messages) based on the work item description. Outputs go to the work item's `## Artifacts` section, Gmail drafts, or OneDrive.

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
- What type of content to draft (email, document, proposal, message, etc.)
- The audience and tone
- Key points to include
- Any templates or examples to follow
- Where the output should go

### 2. Gather Context

Before drafting, gather relevant context:

- **Read related emails**: Search Gmail/Outlook for prior conversations on the topic
- **Check meetings**: Search Fireflies for relevant discussion transcripts
- **Review docs**: Search SharePoint for related documents
- **Check Teams**: Look for relevant team discussions

Use this context to inform the draft — match tone, reference prior discussions, maintain consistency.

### 3. Create Draft

Based on the content type:

#### Email Draft
1. Determine recipients (to, cc, bcc) from work item
2. Draft subject and body
3. Create Gmail draft:
```
mcp__claude_ai_Gmail__gmail_create_draft(
  to="recipient@example.com",
  subject="Subject line",
  body="Email body",
  contentType="text/plain"  # or "text/html" for rich formatting
)
```
4. Write the draft text to `## Artifacts` for reference

#### Document / Proposal / Notes
1. Draft the content following any specified structure
2. Write to `## Artifacts` section of the work item
3. If a Word document is needed, note this for manual OneDrive save

#### Message (Teams, Slack, etc.)
1. Draft the message text
2. Write to `## Artifacts` section
3. User sends manually or instructs Claude to send

### 4. Write to Artifacts

Write the draft to the work item's `## Artifacts` section:

```markdown
### Draft: [Type] — [Subject/Title]

**To:** [Recipients if email]
**Subject:** [Subject if email]
**Type:** [email | document | proposal | message]

---

[Draft content here]

---

**Status:** Draft ready for review
```

### 5. Present for Review

```markdown
## Draft Complete

### Content
- **Type**: [email | document | proposal | message]
- **Subject**: [title/subject]
- **Length**: [word count]

### Actions Taken
- [Gmail draft created / Text written to artifacts / etc.]

### Next Steps
- Review the draft in the work item's Artifacts section
- Edit as needed, then run `/flywheel:done`
- For emails: the Gmail draft is ready to send from your inbox
```

## Output Destinations

| Content Type | Primary Destination | Secondary |
|-------------|-------------------|-----------|
| Email | Gmail draft (`gmail_create_draft`) | `## Artifacts` for reference |
| Document | `## Artifacts` section | OneDrive (Word) if requested |
| Proposal | `## Artifacts` section | OneDrive (Word/PPT) if requested |
| Message | `## Artifacts` section | User sends manually |
| Presentation notes | `## Artifacts` section | OneDrive (PPT) if requested |

## Tips

- **Match the audience** — formal for external, conversational for internal
- **Be concise** — drafts should be ready to send, not verbose
- **Include context** — reference prior conversations when relevant
- **Structure clearly** — use headers, bullet points, clear paragraphs
- **Always write to Artifacts** — even if also creating a Gmail draft, keep a copy in the work item
