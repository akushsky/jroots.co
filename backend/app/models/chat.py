from sqlalchemy import (
    Column,
    Index,
    Integer,
    String,
    Text,
    Boolean,
    ForeignKey,
    DateTime,
    JSON,
    func,
)

from app.models.base import Base


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    is_free = Column(Boolean, nullable=False, default=False, server_default="false")
    tokens_used = Column(Integer, default=0, server_default="0")
    tool_calls = Column(Integer, default=0, server_default="0")
    model_main = Column(String(64), nullable=True)
    status = Column(String(32), default="open", server_default="open")
    created_at = Column(DateTime, server_default=func.now())
    closed_at = Column(DateTime, nullable=True)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("ix_chat_messages_session_created", "session_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    role = Column(String(16), nullable=False)  # user | assistant | system
    content = Column(Text, nullable=False)
    tokens = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class Search(Base):
    __tablename__ = "searches"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    charged = Column(Boolean, default=False, server_default="false")
    query_summary = Column(Text, nullable=True)
    results_count = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class Scan(Base):
    __tablename__ = "scans"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    file_path = Column(String(512), nullable=True)
    status = Column(String(32), nullable=True)
    extracted_text = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    model_used = Column(String(64), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
