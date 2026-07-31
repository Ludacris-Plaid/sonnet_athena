"""
RealtyAI Compliance MCP Server.

Exposes fair housing screening, disclosure reference lookup, AML overview,
and protected-class reference as MCP tools — usable from Claude Desktop,
Claude Code, or any other MCP client.

Run directly (stdio transport, the standard for local MCP clients):
    python server.py

Register with Claude Desktop by adding to claude_desktop_config.json:
    {
      "mcpServers": {
        "realtyai-compliance": {
          "command": "python",
          "args": ["/absolute/path/to/mcp_server/server.py"],
          "env": { "DEEPSEEK_API_KEY": "your_key_here" }
        }
      }
    }

For DeepSeek specifically: DeepSeek's API doesn't speak MCP (MCP is
consumed by Claude clients) — but DeepSeek's chat completion API is
OpenAI-compatible and supports function/tool calling. See
deepseek_bridge.py in this same directory for a working example that
exposes these exact same tools to DeepSeek via its `tools` parameter.
"""
from mcp.server.fastmcp import FastMCP

from compliance_logic import (
    screen_listing_text,
    get_disclosure_reference,
    get_aml_overview,
    get_protected_classes,
)

mcp = FastMCP("realtyai-compliance")


@mcp.tool()
def screen_listing_for_fair_housing(text: str) -> dict:
    """
    Screen real estate listing/advertising text for language that could
    violate US federal Fair Housing Act or Canadian provincial human rights
    code protections. Returns flagged phrases with explanations and an
    overall risk level. This is an automated first-pass check, not legal
    advice — always confirm with brokerage compliance/legal counsel.
    """
    return screen_listing_text(text)


@mcp.tool()
def get_disclosure_checklist(jurisdiction: str) -> dict:
    """
    Get a general, non-exhaustive reference of common seller disclosure
    requirements for a jurisdiction. Valid codes: US-generic, US-CA, US-TX,
    US-NY, US-FL, CA-ON, CA-BC, CA-AB. This is illustrative only — always
    verify current requirements with the relevant state/provincial
    regulator or the brokerage's legal counsel before relying on it.
    """
    return get_disclosure_reference(jurisdiction)


@mcp.tool()
def get_anti_money_laundering_overview(country: str) -> dict:
    """
    Get a summary of anti-money-laundering reporting obligations relevant
    to real estate professionals. country must be "US" or "CA". Note: US
    federal rules in this space are currently contested in court (status
    can change) — always verify current status at the authoritative source
    URL included in the response before advising a client.
    """
    return get_aml_overview(country)


@mcp.tool()
def get_fair_housing_protected_classes(country: str) -> dict:
    """
    List the protected classes/grounds relevant to housing discrimination
    law. country must be "US" (federal Fair Housing Act) or "CA"
    (representative list — actual law is set provincially in Canada).
    """
    return get_protected_classes(country)


if __name__ == "__main__":
    mcp.run(transport="stdio")
