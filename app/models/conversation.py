import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import Column, String, DateTime, ForeignKey, Boolean, Enum, JSON, Text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class ConversationContext(str, PyEnum):
    CHAT = "chat"                # regular "Chat with Athena"
    ADMIN_AGENT = "admin_agent"  # the platform admin's own Athena (god-mode agent)


class ConversationRole(str, PyEnum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class Conversation(Base):
    """
    A persistent, ongoing conversation thread. The core behavior this
    enables: chat is NEVER lost or reset just because a page reloaded or a
    session ended — it only resets when the user explicitly starts a new
    conversation (see conversation_service.start_new_conversation()).
    Exactly one conversation per (user_id, context) is "active" at a time
    — that's the one new turns get appended to and the one that loads by
    default.
    """
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    context = Column(Enum(ConversationContext), default=ConversationContext.CHAT, nullable=False)

    title = Column(String, nullable=True)  # auto-set from the first user message, editable later if a UI for that is added
    is_active = Column(Boolean, default=True)  # the one currently being appended to / loaded by default

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_message_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False)

    role = Column(Enum(ConversationRole), nullable=False)
    content = Column(Text, nullable=True)  # nullable: a tool-calling turn may have tool_calls but no content
    tool_calls = Column(JSON, nullable=True)  # for the admin agent's function-calling turns
    tool_call_id = Column(String, nullable=True)  # for role=tool messages, matches the originating tool_call's id

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
