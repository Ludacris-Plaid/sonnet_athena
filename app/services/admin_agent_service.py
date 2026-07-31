"""
The admin's own Athena — "god mode with guardrails." Full power over the
platform (user/org management, stats), scoped through a curated set of
tools rather than raw database/SQL access, with two real, server-enforced
guardrails:

1. NO SQL, no raw ORM access exposed to the model. Every capability is a
   specific Python function with its own validation (see admin_service.py) —
   the model can suspend a user, it cannot "run a query."

2. Destructive actions require a REAL two-step confirmation, not just a
   prompt instruction the model could skip. The first call to a destructive
   tool returns a confirmation_token and does NOT act. The model must call
   the same tool again with that exact token to actually execute. This
   can't be bypassed by a model (or a prompt-injected instruction) simply
   deciding to "confirm" on the first pass, since it doesn't know the token
   in advance — the token only exists after the server has already decided
   to ask.

Known limitation: pending confirmations are stored in-memory
(_PENDING_CONFIRMATIONS below), which is fine for a single-process
deployment but won't work across multiple API instances — move this to
Redis or a DB table if you scale horizontally.
"""
import secrets
import time
import json

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.org import User
from app.services import admin_service
from app.services import conversation_service
from app.services.llm_service import llm_service

_PENDING_CONFIRMATIONS: dict[str, dict] = {}
_CONFIRMATION_TTL_SECONDS = 300

DESTRUCTIVE_ACTIONS = {"suspend_user", "ban_user", "adjust_plan_tier", "deactivate_organization"}

SYSTEM_PROMPT = """You are Athena, acting as the platform administrator's own \
assistant — not a customer-facing assistant. You have real tools to manage \
users and organizations across the entire platform.

Rules you must follow:
- For any DESTRUCTIVE action (suspending or banning a user, changing an \
organization's plan tier, deactivating an organization), the tool will \
return a confirmation_token instead of acting the first time. Tell the \
admin clearly what you're about to do and why, then wait for them to \
explicitly say to proceed before calling the tool again with that same \
confirmation_token.
- Never fabricate user or organization data — always call a tool to look \
something up rather than guessing.
- Always state which user/org (by name/email, not just ID) an action will \
affect, so the admin can catch a mistake before confirming.
"""

TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "get_platform_stats",
        "description": "Get platform-wide financial and usage statistics (MRR, token usage, user counts by status, plan tier breakdown).",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "search_users",
        "description": "Search/list users by name or email, optionally filtered by status.",
        "parameters": {"type": "object", "properties": {
            "search": {"type": "string", "description": "Name or email substring to search for. Omit to list all."},
            "status": {"type": "string", "enum": ["active", "suspended", "banned"]},
        }},
    }},
    {"type": "function", "function": {
        "name": "suspend_user",
        "description": "Suspend a user (temporary, reversible). DESTRUCTIVE — requires confirmation.",
        "parameters": {"type": "object", "properties": {
            "user_id": {"type": "string"},
            "reason": {"type": "string"},
            "confirmation_token": {"type": "string", "description": "Only include on the second call, after the admin confirmed."},
        }, "required": ["user_id", "reason"]},
    }},
    {"type": "function", "function": {
        "name": "ban_user",
        "description": "Ban a user (for cause, more severe than suspend). DESTRUCTIVE — requires confirmation.",
        "parameters": {"type": "object", "properties": {
            "user_id": {"type": "string"},
            "reason": {"type": "string"},
            "confirmation_token": {"type": "string"},
        }, "required": ["user_id", "reason"]},
    }},
    {"type": "function", "function": {
        "name": "reinstate_user",
        "description": "Reinstate a suspended or banned user back to active. Not destructive — reversing a restriction — no confirmation needed.",
        "parameters": {"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]},
    }},
    {"type": "function", "function": {
        "name": "adjust_plan_tier",
        "description": "Change an organization's subscription plan tier. DESTRUCTIVE (billing-affecting) — requires confirmation.",
        "parameters": {"type": "object", "properties": {
            "org_id": {"type": "string"},
            "new_tier": {"type": "string", "enum": ["light", "medium", "heavy"]},
            "confirmation_token": {"type": "string"},
        }, "required": ["org_id", "new_tier"]},
    }},
    {"type": "function", "function": {
        "name": "deactivate_organization",
        "description": "Deactivate an organization entirely (all its users lose access). DESTRUCTIVE — requires confirmation.",
        "parameters": {"type": "object", "properties": {
            "org_id": {"type": "string"},
            "confirmation_token": {"type": "string"},
        }, "required": ["org_id"]},
    }},
]


def _request_confirmation(action: str, params: dict, description: str) -> dict:
    token = secrets.token_urlsafe(16)
    _PENDING_CONFIRMATIONS[token] = {"action": action, "params": params, "expires_at": time.time() + _CONFIRMATION_TTL_SECONDS}
    return {"status": "confirmation_required", "confirmation_token": token, "message": description}


def _check_confirmation(token: str | None, action: str, params: dict) -> bool:
    if not token:
        return False
    pending = _PENDING_CONFIRMATIONS.get(token)
    if not pending or pending["action"] != action or time.time() > pending["expires_at"]:
        return False
    del _PENDING_CONFIRMATIONS[token]  # single use
    return True


def _dispatch_tool(db: Session, admin: User, name: str, args: dict) -> dict:
    if name == "get_platform_stats":
        return admin_service.get_platform_overview(db)

    if name == "search_users":
        users = admin_service.list_all_users(db, search=args.get("search"), status=args.get("status"))
        return {"users": [{"id": str(u.id), "name": u.full_name, "email": u.email, "status": u.status, "org_id": str(u.org_id)} for u in users[:25]]}

    if name in ("suspend_user", "ban_user"):
        status_map = {"suspend_user": "suspended", "ban_user": "banned"}
        new_status = status_map[name]
        params = {"user_id": args["user_id"], "reason": args.get("reason", "")}
        if not _check_confirmation(args.get("confirmation_token"), name, params):
            target = admin_service.get_user(db, args["user_id"])
            target_desc = f"{target.full_name} ({target.email})" if target else args["user_id"]
            return _request_confirmation(name, params, f"About to set {target_desc} to '{new_status}'. Reason: {args.get('reason', '(none given)')}. Confirm to proceed.")
        user = admin_service.update_user_status(db, admin, args["user_id"], new_status, args.get("reason"), source="agent")
        return {"status": "done", "user_id": str(user.id), "new_status": user.status}

    if name == "reinstate_user":
        user = admin_service.update_user_status(db, admin, args["user_id"], "active", "Reinstated via admin agent", source="agent")
        return {"status": "done", "user_id": str(user.id), "new_status": user.status}

    if name == "adjust_plan_tier":
        params = {"org_id": args["org_id"], "new_tier": args["new_tier"]}
        if not _check_confirmation(args.get("confirmation_token"), name, params):
            return _request_confirmation(name, params, f"About to change org {args['org_id']}'s plan to '{args['new_tier']}'. Confirm to proceed.")
        org = admin_service.adjust_plan_tier(db, admin, args["org_id"], args["new_tier"], source="agent")
        return {"status": "done", "org_id": str(org.id), "new_tier": org.plan_tier.value}

    if name == "deactivate_organization":
        params = {"org_id": args["org_id"]}
        if not _check_confirmation(args.get("confirmation_token"), name, params):
            return _request_confirmation(name, params, f"About to deactivate org {args['org_id']} — ALL its users will lose access. Confirm to proceed.")
        org = admin_service.set_org_active(db, admin, args["org_id"], False, source="agent")
        return {"status": "done", "org_id": str(org.id), "is_active": org.is_active}

    return {"error": f"Unknown tool: {name}"}


def run_admin_chat(db: Session, admin: User, conversation_id: str, user_message: str) -> dict:
    """
    One turn of the admin agent conversation, with a tool-calling loop.
    History is loaded from the persisted Conversation (see
    conversation_service.py) rather than passed in by the caller — this is
    what makes the admin's Athena subject to the same "never resets unless
    explicitly asked" rule as the regular chat, instead of losing context
    every time the browser tab closes.
    """
    conversation_service.add_message(db, conversation_id, "user", user_message)

    history = conversation_service.get_conversation_messages(db, conversation_id)
    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in history:
        entry = {"role": m.role.value, "content": m.content}
        if m.tool_calls:
            entry["tool_calls"] = m.tool_calls
        if m.tool_call_id:
            entry["tool_call_id"] = m.tool_call_id
        full_messages.append(entry)

    for _ in range(5):
        response = llm_service.complete_with_tools(full_messages, TOOL_SCHEMAS)
        tool_calls = response.get("tool_calls")

        if not tool_calls:
            conversation_service.add_message(db, conversation_id, "assistant", response["content"])
            return {"reply": response["content"]}

        full_messages.append({"role": "assistant", "content": response.get("content"), "tool_calls": tool_calls})
        conversation_service.add_message(db, conversation_id, "assistant", response.get("content"), tool_calls=tool_calls)

        for call in tool_calls:
            args = json.loads(call["function"]["arguments"])
            result = _dispatch_tool(db, admin, call["function"]["name"], args)
            tool_content = json.dumps(result)
            full_messages.append({"role": "tool", "tool_call_id": call["id"], "content": tool_content})
            conversation_service.add_message(db, conversation_id, "tool", tool_content, tool_call_id=call["id"])

    return {"reply": "Reached tool-call iteration limit without a final answer."}
