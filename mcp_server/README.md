# RealtyAI Compliance MCP Server

Fair housing screening, disclosure reference, and AML overview tools,
exposed two ways:

1. **As an MCP server** (`server.py`) — for Claude Desktop, Claude Code, or
   any other MCP client.
2. **As a DeepSeek function-calling bridge** (`deepseek_bridge.py`) — since
   DeepSeek's API doesn't speak MCP, but is OpenAI-compatible and supports
   `tools`/function calling, which is the equivalent mechanism.

Both wrap the same underlying logic in `compliance_logic.py` +
`compliance_data.py`, kept deliberately self-contained (no dependency on the
main `app/` package) so this can be deployed as its own small service.

## What this is NOT

This is a compliance-**assistance** layer, not a compliance guarantee. Real
estate law is jurisdiction-specific and changes — the AML overview tool
covers a rule that was literally vacated by a federal court weeks after it
took effect. Every tool response carries a disclaimer for a reason: use
this to catch obvious issues fast, not as a substitute for the brokerage's
compliance officer or a lawyer licensed in the relevant jurisdiction.

## Setup

```bash
cd mcp_server
pip install -r requirements.txt --break-system-packages
export DEEPSEEK_API_KEY=your_key_here
```

## Option 1: Use with Claude Desktop / Claude Code (MCP)

Add to your MCP client's config (e.g. `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "realtyai-compliance": {
      "command": "python",
      "args": ["/absolute/path/to/mcp_server/server.py"],
      "env": { "DEEPSEEK_API_KEY": "your_key_here" }
    }
  }
}
```

Restart the client. It will discover four tools:
`screen_listing_for_fair_housing`, `get_disclosure_checklist`,
`get_anti_money_laundering_overview`, `get_fair_housing_protected_classes`.

## Option 2: Use with DeepSeek directly

```bash
python deepseek_bridge.py
```

This runs a demo conversation where DeepSeek is given the same four tools
via its `tools` parameter, decides to call `screen_listing_for_fair_housing`,
and answers grounded in the actual result rather than guessing.

To wire this into the main RealtyAI chat orchestrator instead of running it
standalone: import `TOOL_SCHEMAS` and `dispatch_tool_call` from
`deepseek_bridge.py` into `app/services/orchestrator_service.py`, pass
`TOOL_SCHEMAS` as the `tools` param on the relevant `llm_service.complete()`
call, and route any `tool_calls` in the response through `dispatch_tool_call`
before returning to the user — the same loop `chat_with_tools()` already
implements here.

## Files

- `server.py` — MCP server (stdio transport)
- `deepseek_bridge.py` — DeepSeek tool-calling bridge + demo
- `compliance_logic.py` — keyword scan + LLM contextual review + lookups
- `compliance_data.py` — reference data (protected classes, flagged phrases,
  disclosure reference, AML overview) — see the "last reviewed" note at the
  top of that file and re-verify before trusting it in production
