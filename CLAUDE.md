# btc-claude-plugins

Claude Code plugin marketplace for Bellwether Technology.

## Project structure

- `.claude-plugin/marketplace.json` — marketplace manifest listing all plugins
- `plugins/` — each subdirectory is a self-contained plugin

## Conventions

- Plugin names use kebab-case (e.g., `connectwise-tools`)
- Every plugin must have `.claude-plugin/plugin.json` with name, description, version
- Use semantic versioning for plugin versions
- Update `marketplace.json` when adding/removing plugins
- Keep plugins self-contained — no cross-plugin imports

## Adding a plugin

1. Create `plugins/<plugin-name>/`
2. Create `plugins/<plugin-name>/.claude-plugin/plugin.json`
3. Add components (commands/, agents/, skills/, hooks/, .mcp.json)
4. Add entry to `.claude-plugin/marketplace.json`

## Pre-commit checks

- Validate that `marketplace.json` is valid JSON
- Ensure every plugin listed in `marketplace.json` has a corresponding directory
- Ensure every plugin directory has a valid `plugin.json`
