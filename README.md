# btc-claude-plugins

Claude Code plugin marketplace for Bellwether internal plugins.

## What is this?

This repo is a Claude Code plugin marketplace — a catalog of internally-developed plugins that extend Claude Code with custom skills, agents, hooks, and MCP server bundles.

## Installing plugins from this marketplace

In Claude Code, run:

```
/plugin install <plugin-name>@btc-claude-plugins
```

To browse available plugins, check the `plugins/` directory or view `.claude-plugin/marketplace.json`.

## Adding a new plugin

1. Create a new directory under `plugins/` with your plugin name (kebab-case)
2. Add a `.claude-plugin/plugin.json` manifest inside your plugin directory
3. Add your plugin's components (commands, agents, skills, hooks, MCP configs)
4. Register your plugin in `.claude-plugin/marketplace.json`
5. Open a PR for review

### Plugin directory structure

```
plugins/my-plugin/
├── .claude-plugin/
│   └── plugin.json          # Plugin manifest (required)
├── commands/                 # Markdown skill files
├── agents/                   # Subagent definitions
├── skills/                   # Agent skills with SKILL.md
├── hooks/                    # Event handlers (hooks.json)
├── .mcp.json                 # MCP server configurations
└── settings.json             # Default plugin settings
```

### Plugin manifest (`plugin.json`)

```json
{
  "name": "my-plugin",
  "description": "What the plugin does",
  "version": "1.0.0",
  "author": {
    "name": "Your Name",
    "email": "you@bellwethertech.com"
  },
  "keywords": ["relevant", "tags"]
}
```

## Marketplace manifest

The `.claude-plugin/marketplace.json` file catalogs all available plugins. Each entry references a plugin by its relative path in this repo:

```json
{
  "name": "btc-claude-plugins",
  "owner": {
    "name": "Bellwether Technology",
    "email": "dev@bellwethertech.com"
  },
  "plugins": [
    {
      "name": "my-plugin",
      "source": "./plugins/my-plugin",
      "description": "What it does",
      "version": "1.0.0"
    }
  ]
}
```
