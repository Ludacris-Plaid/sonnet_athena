"""
Slack integration: verify inbound Events API requests are really from
Slack (HMAC signature per Slack's documented v0 signing process), route
messages/mentions through the same chat orchestrator everything else uses,
and post system notifications (alerts) to a configured channel.

Deliberately minimal scope, per the request: chat with Athena via Slack
and get system notifications there — not a full Slack app with slash
commands, home tabs, or interactive components.
"""
import hashlib
import hmac
import time

import httpx

from app.core.config import settings
from app.models.org import Organization
from app.services.crm_credential_service import decrypt_credentials


def verify_slack_signature(headers: dict, raw_body: bytes) -> bool:
    timestamp = headers.get("x-slack-request-timestamp", "")
    signature = headers.get("x-slack-signature", "")
    if not timestamp or not signature:
        return False
    if abs(time.time() - int(timestamp)) > 60 * 5:  # reject requests older than 5 minutes (replay protection)
        return False

    base = f"v0:{timestamp}:{raw_body.decode()}"
    computed = "v0=" + hmac.new(settings.SLACK_SIGNING_SECRET.encode(), base.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, signature)


def handle_event(db, connection, event: dict, org_id: str, default_user_id: str) -> None:
    """
    Routes a Slack message/mention through the SAME real tool-calling agent
    (athena_agent_service) and the SAME persistent conversation thread as
    web chat and voice — "wherever you talk to Athena, it's one ongoing
    relationship," not a separate history per channel. Replies in-thread.
    """
    from app.models.org import User
    from app.services import conversation_service
    from app.services.athena_agent_service import run_athena_chat

    text = event.get("text", "")
    channel = event.get("channel")
    if not text or not channel:
        return

    user = db.query(User).filter(User.id == default_user_id).first()
    if not user:
        return

    conv = conversation_service.get_or_create_active_conversation(db, org_id, default_user_id, context="chat")
    result = run_athena_chat(db, user, str(conv.id), text)
    post_message(connection, channel, result["reply"], thread_ts=event.get("ts"))


def post_message(connection, channel: str, text: str, thread_ts: str | None = None) -> None:
    tokens = decrypt_credentials(connection.encrypted_tokens)
    payload = {"channel": channel, "text": text}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    with httpx.Client(timeout=15) as client:
        client.post(
            "https://slack.com/api/chat.postMessage",
            json=payload,
            headers={"Authorization": f"Bearer {tokens['bot_token']}"},
        )


def notify_org(db, org_id: str, text: str) -> bool:
    """Posts a system notification (e.g. a critical alert) to the org's configured Slack channel, if connected."""
    from app.models.email_connection import SlackConnection  # local import avoids a hard dependency at module load if unused

    connection = db.query(SlackConnection).filter(SlackConnection.org_id == org_id, SlackConnection.is_active == True).first()  # noqa: E712
    if not connection or not connection.notification_channel_id:
        return False
    post_message(connection, connection.notification_channel_id, text)
    return True
