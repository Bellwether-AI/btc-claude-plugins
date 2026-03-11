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

The daemon auto-restarts on crash (up to 5 retries). It must be restarted via `launchctl` — do NOT use `kill` directly, as launchd will just respawn it and you may get port conflicts on 9753.

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

Wait 2 seconds, then:

```bash
launchctl load ~/Library/LaunchAgents/com.flywheel.agent.plist
```

3. **Verify the restart** by reading the last 15 lines of the log file at `~/.flywheel/logs/agent.log`. Confirm you see:
   - `Flywheel Agent starting...`
   - `Hook server listening on http://127.0.0.1:9753`
   - `Connected to Flywheel hub`
   - `Discovered N projects: ...`

If the log shows `EADDRINUSE` on port 9753, the previous process hasn't fully stopped. Wait a few more seconds and try the `launchctl load` again.

4. **Report the result** to the user — success or any errors seen in the log.
