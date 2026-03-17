---
description: Rebuild and restart the Flywheel agent daemon
---
# Flywheel: Restart Agent

Rebuild and restart the Flywheel agent daemon.

## Architecture

The Flywheel agent is a Node.js daemon managed by macOS launchd:

- **Source**: `~/personal/flywheel/agent/`
- **Build**: `npm run build` (TypeScript → `dist/`)
- **Launch agent plist**: `~/Library/LaunchAgents/com.flywheel.agent.plist`
- **Log file**: `~/.flywheel/logs/agent.log`
- **Hook server**: Listens on `http://127.0.0.1:9753`
- **Connects to**: Azure SignalR hub at `https://www.flywheelgsd.com`

The daemon auto-restarts on crash (up to 5 retries). It must be restarted via `launchctl` only — **never** use `kill`, `lsof`, or any process-killing commands on port 9753. `lsof -ti :9753` returns both the agent AND any Claude Code processes connected to the hook server. Killing a PID from that list may kill your own Claude Code session.

## Steps

1. **Build the agent**:

```bash
npm run build --prefix ~/personal/flywheel/agent
```

If the build fails, fix the TypeScript errors before proceeding.

2. **Restart via launchctl**:

```bash
launchctl unload ~/Library/LaunchAgents/com.flywheel.agent.plist
```

Wait 5 seconds (allows the process to fully release port 9753), then:

```bash
launchctl load ~/Library/LaunchAgents/com.flywheel.agent.plist
```

3. **Verify the restart** by reading the last 15 lines of the log file at `~/.flywheel/logs/agent.log`. Confirm you see:
   - `Flywheel Agent starting...`
   - `Hook server listening on http://127.0.0.1:9753`
   - `Connected to Flywheel hub`
   - `Discovered N projects: ...`

If the log shows `EADDRINUSE` on port 9753, the previous process hasn't fully stopped. Handle this with **only** `launchctl` — never use `kill` or `lsof` to find/kill processes on this port (see Architecture note above).

Recovery steps for EADDRINUSE:
  1. `launchctl unload ~/Library/LaunchAgents/com.flywheel.agent.plist`
  2. Wait 5 seconds (the process needs time to release the port after SIGTERM)
  3. `launchctl load ~/Library/LaunchAgents/com.flywheel.agent.plist`
  4. Wait 3 seconds and re-check the log
  5. If still failing after 2 retry cycles, **stop and ask the user** — do not escalate to `kill`

4. **Report the result** to the user — success or any errors seen in the log.
