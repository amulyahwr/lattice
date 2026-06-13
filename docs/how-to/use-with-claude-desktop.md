# Use with Claude Desktop

Lattice can serve as a persistent memory layer for Claude Desktop, the same way it does for Claude Code.

!!! note "Status"
    This guide is a stub. Claude Desktop uses the same MCP protocol — configuration steps coming soon.

## Quick start

Add Lattice to Claude Desktop's MCP server list in `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "lattice": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/lattice-repo", "lattice"],
      "env": {
        "LLM_PROVIDER": "ollama",
        "LLM_MODEL": "gemma4",
        "LATTICE_DIR": "/Users/yourname/.lattice"
      }
    }
  }
}
```

Restart Claude Desktop. The Lattice tools (`lattice_ingest`, `lattice_answer`, etc.) will appear as available tools in conversations.

See [MCP Tools Reference](../reference/mcp-tools.md) for what each tool does.
