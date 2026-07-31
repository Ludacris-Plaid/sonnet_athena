"""
Exposes the same compliance tools to DeepSeek via its OpenAI-compatible
function/tool-calling API. DeepSeek doesn't speak MCP (Model Context
Protocol is consumed by Claude clients) — this bridge is the equivalent
mechanism for DeepSeek: define tool JSON schemas, let DeepSeek's model
decide when to call them, execute locally, feed results back.

Run this file directly for a demo conversation loop:
    export DEEPSEEK_API_KEY=your_key
    python deepseek_bridge.py

Or import TOOL_SCHEMAS + dispatch_tool_call() into the main RealtyAI
backend's orchestrator_service.py to give the chat/voice assistant direct
access to compliance checks mid-conversation.
"""
import json
import os

import httpx

from compliance_logic import (
    screen_listing_text,
    get_disclosure_reference,
    get_aml_overview,
    get_protected_classes,
)

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

# OpenAI-compatible tool schema — DeepSeek's API accepts this exact shape.
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "screen_listing_for_fair_housing",
            "description": "Screen real estate listing text for language that could violate US Fair Housing Act or Canadian human rights code protections. Not legal advice — a first-pass check only.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string", "description": "The listing/advertising text to screen."}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_disclosure_checklist",
            "description": "Get a general, non-exhaustive reference of seller disclosure requirements for a jurisdiction. Illustrative only, not legal advice.",
            "parameters": {
                "type": "object",
                "properties": {
                    "jurisdiction": {
                        "type": "string",
                        "description": "One of: US-generic, US-CA, US-TX, US-NY, US-FL, CA-ON, CA-BC, CA-AB",
                    }
                },
                "required": ["jurisdiction"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_anti_money_laundering_overview",
            "description": "Get a summary of AML reporting obligations for real estate professionals in the US or Canada. Status of US rules can be contested/changing — verify before advising a client.",
            "parameters": {
                "type": "object",
                "properties": {"country": {"type": "string", "description": "'US' or 'CA'"}},
                "required": ["country"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_fair_housing_protected_classes",
            "description": "List protected classes/grounds relevant to housing discrimination law for a country.",
            "parameters": {
                "type": "object",
                "properties": {"country": {"type": "string", "description": "'US' or 'CA'"}},
                "required": ["country"],
            },
        },
    },
]

_DISPATCH_TABLE = {
    "screen_listing_for_fair_housing": lambda args: screen_listing_text(args["text"]),
    "get_disclosure_checklist": lambda args: get_disclosure_reference(args["jurisdiction"]),
    "get_anti_money_laundering_overview": lambda args: get_aml_overview(args["country"]),
    "get_fair_housing_protected_classes": lambda args: get_protected_classes(args["country"]),
}


def dispatch_tool_call(name: str, arguments_json: str) -> dict:
    """Executes a tool call DeepSeek requested, given its name and JSON-string arguments."""
    if name not in _DISPATCH_TABLE:
        return {"error": f"Unknown tool: {name}"}
    args = json.loads(arguments_json)
    return _DISPATCH_TABLE[name](args)


def chat_with_tools(messages: list[dict]) -> str:
    """
    Runs one DeepSeek conversation turn with tool-calling enabled, executing
    any tool calls the model requests and feeding results back until it
    produces a final text answer. Simple synchronous loop — no streaming.
    """
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY not set in environment")

    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}

    for _ in range(5):  # cap iterations so a tool-calling loop can't run forever
        payload = {"model": DEEPSEEK_MODEL, "messages": messages, "tools": TOOL_SCHEMAS, "temperature": 0.2}
        with httpx.Client(timeout=60) as client:
            resp = client.post(f"{DEEPSEEK_BASE_URL}/v1/chat/completions", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]["message"]
        tool_calls = choice.get("tool_calls")

        if not tool_calls:
            return choice["content"]

        messages.append(choice)
        for call in tool_calls:
            result = dispatch_tool_call(call["function"]["name"], call["function"]["arguments"])
            messages.append(
                {"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result)}
            )

    return "Reached tool-call iteration limit without a final answer."


if __name__ == "__main__":
    demo_messages = [
        {"role": "system", "content": "You are Athena, a real estate compliance assistant. Use the available tools to answer accurately rather than guessing."},
        {"role": "user", "content": "Can I advertise a rental as 'adults only, no children, walking distance to a great Christian church'? I'm listing in Ontario."},
    ]
    print(chat_with_tools(demo_messages))
