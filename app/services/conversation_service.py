"""
Persistent conversation management. Core rule, enforced here and nowhere
else (routes/services calling in don't need to think about it): a
conversation is NEVER reset, archived, or lost except through an explicit
call to start_new_conversation() — a page reload, a new login session, a
server restart, none of that touches conversation state. Everything is
just... still there, the way a real ongoing relationship would be.
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.conversation import Conversation, ConversationMessage, ConversationContext, ConversationRole


def get_active_conversation(db: Session, user_id: str, context: str = "chat") -> Conversation | None:
    return (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id, Conversation.context == context, Conversation.is_active == True)  # noqa: E712
        .order_by(Conversation.last_message_at.desc())
        .first()
    )


def get_or_create_active_conversation(db: Session, org_id: str, user_id: str, context: str = "chat") -> Conversation:
    existing = get_active_conversation(db, user_id, context)
    if existing:
        return existing

    conv = Conversation(org_id=org_id, user_id=user_id, context=context, is_active=True)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def start_new_conversation(db: Session, org_id: str, user_id: str, context: str = "chat") -> Conversation:
    """
    The ONLY reset mechanism in the system. Deactivates whatever
    conversation was active (it's NOT deleted — still fully there,
    searchable, resumable) and creates a fresh active one.
    """
    db.query(Conversation).filter(
        Conversation.user_id == user_id, Conversation.context == context, Conversation.is_active == True  # noqa: E712
    ).update({"is_active": False})

    conv = Conversation(org_id=org_id, user_id=user_id, context=context, is_active=True)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def activate_conversation(db: Session, user_id: str, conversation_id: str) -> Conversation:
    """Switch back to an old (inactive) conversation — resuming it, not resetting anything."""
    target = db.query(Conversation).filter(Conversation.id == conversation_id, Conversation.user_id == user_id).first()
    if not target:
        raise ValueError("Conversation not found")

    db.query(Conversation).filter(
        Conversation.user_id == user_id, Conversation.context == target.context, Conversation.is_active == True  # noqa: E712
    ).update({"is_active": False})

    target.is_active = True
    db.add(target)
    db.commit()
    db.refresh(target)
    return target


def add_message(db: Session, conversation_id: str, role: str, content: str | None, tool_calls: list | None = None, tool_call_id: str | None = None) -> ConversationMessage:
    msg = ConversationMessage(conversation_id=conversation_id, role=role, content=content, tool_calls=tool_calls, tool_call_id=tool_call_id)
    db.add(msg)

    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if conv:
        conv.last_message_at = datetime.now(timezone.utc)
        # Auto-title from the first real user message, so the conversation
        # list (see routes_conversations.py) shows something meaningful
        # instead of every entry saying "Untitled".
        if not conv.title and role == "user" and content:
            conv.title = content[:60] + ("…" if len(content) > 60 else "")
        db.add(conv)

    db.commit()
    db.refresh(msg)
    return msg


def get_conversation_messages(db: Session, conversation_id: str) -> list[ConversationMessage]:
    return db.query(ConversationMessage).filter(ConversationMessage.conversation_id == conversation_id).order_by(ConversationMessage.created_at).all()


def list_conversations(db: Session, user_id: str, context: str = "chat", search: str | None = None) -> list[Conversation]:
    query = db.query(Conversation).filter(Conversation.user_id == user_id, Conversation.context == context)
    if search:
        # Searches both the conversation title and any message content
        # within it — a search term buried in message 40 of a long thread
        # should still surface that conversation.
        matching_conv_ids = (
            db.query(ConversationMessage.conversation_id)
            .filter(ConversationMessage.content.ilike(f"%{search}%"))
            .distinct()
        )
        query = query.filter((Conversation.title.ilike(f"%{search}%")) | (Conversation.id.in_(matching_conv_ids)))
    return query.order_by(Conversation.last_message_at.desc()).all()
