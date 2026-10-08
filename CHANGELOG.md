# Changelog

## 2026-10-07 — plugins moved

- `README.md`: new "Moved plugins" section naming `co-dwerker` (frozen at 1.2.0) and `claude-extra-usage-limiter-bellwether` (frozen at 1.0.0), with the install commands for https://github.com/Bellwether-Technology/bellwether-claude-plugins. Reason: both plugins are now maintained there.
- `.claude-plugin/marketplace.json`: the two plugins' descriptions begin with a MOVED notice so `/plugin` shows it; versions left unchanged so they match the point the new repo started from.
- `plugins/co-dwerker/.claude-plugin/plugin.json`, `plugins/claude-extra-usage-limiter-bellwether/.claude-plugin/plugin.json`: same MOVED notice in `description`.
- `plugins/co-dwerker/README.md`, `plugins/claude-extra-usage-limiter-bellwether/README.md`: "Moved" banner under the title.
- `RELEASE_NOTES.md`: "Plugins moved" section.
- `CHANGELOG.md`: created.
