"""
Sanaa AI — Database Models
PostgreSQL + pgvector for hybrid memory search.
"""

import os
import json
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, Float, Boolean,
    DateTime, JSON, select, desc, func, Index, text,
)

from config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url_async, echo=False, pool_size=10, max_overflow=20)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def utcnow():
    return datetime.now(timezone.utc)


# ==================== MIXIN ====================

class ActiveRecordMixin:
    """Convenience methods for simple CRUD operations."""

    @classmethod
    async def create(cls, **kwargs):
        async with AsyncSessionLocal() as session:
            instance = cls(**kwargs)
            session.add(instance)
            await session.commit()
            await session.refresh(instance)
            return instance

    @classmethod
    async def get(cls, id):
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(cls).where(cls.id == id))
            return result.scalars().first()

    @classmethod
    async def get_recent(cls, limit=10):
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(cls).order_by(desc(cls.created_at)).limit(limit)
            )
            return result.scalars().all()

    @classmethod
    async def update_by_id(cls, id, **kwargs):
        async with AsyncSessionLocal() as session:
            instance = await session.get(cls, id)
            if instance:
                for key, value in kwargs.items():
                    setattr(instance, key, value)
                await session.commit()
                return instance
            return None


# ==================== EXISTING TABLES (Phase 1) ====================

class Log(Base, ActiveRecordMixin):
    __tablename__ = "logs"
    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(100), nullable=False)
    level = Column(String(20), nullable=False, default="info")
    message = Column(Text, nullable=False)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class Command(Base, ActiveRecordMixin):
    __tablename__ = "commands"
    id = Column(String(32), primary_key=True, default=lambda: os.urandom(8).hex())
    user_id = Column(String(100), nullable=True)
    channel = Column(String(50), default="web")
    text = Column(Text, nullable=False)
    context = Column(Text, nullable=True)
    status = Column(String(20), default="pending")
    proposed_plan = Column(JSON, nullable=True)
    results = Column(JSON, nullable=True)
    thinking = Column(Text, nullable=True)
    tools_used = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class DeviceReport(Base, ActiveRecordMixin):
    __tablename__ = "device_reports"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(100), nullable=False, index=True)
    device_name = Column(String(200), nullable=True)
    data = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    @classmethod
    async def get_latest_all(cls):
        """Get latest report per device."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(cls).order_by(desc(cls.created_at)).limit(50)
            )
            reports = result.scalars().all()
            latest = {}
            for r in reports:
                if r.device_id not in latest:
                    latest[r.device_id] = r
            return list(latest.values())


class Alert(Base, ActiveRecordMixin):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True, index=True)
    severity = Column(String(20), nullable=False)
    source = Column(String(100), nullable=True)
    title = Column(String(500), nullable=True)
    message = Column(Text, nullable=False)
    metric = Column(String(50), nullable=True)
    acknowledged = Column(Boolean, default=False)
    acknowledged_by = Column(String(100), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)


# ==================== NEW TABLES ====================

class AgentMemory(Base, ActiveRecordMixin):
    """Long-term knowledge store with vector embeddings for hybrid search."""
    __tablename__ = "agent_memory"
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    category = Column(String(50), nullable=False, index=True)  # fact, preference, procedure, observation
    content = Column(Text, nullable=False)
    source = Column(String(200), nullable=True)
    confidence = Column(Float, default=0.5)
    verified = Column(Boolean, default=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    access_count = Column(Integer, default=0)
    last_accessed_at = Column(DateTime(timezone=True), nullable=True)
    metadata_ = Column("metadata", JSON, nullable=True)
    # Note: embedding column added via raw SQL migration (pgvector type)


class SystemKnowledge(Base, ActiveRecordMixin):
    """Infrastructure facts auto-populated by agents."""
    __tablename__ = "system_knowledge"
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    domain = Column(String(100), nullable=False)  # server, database, application, network
    key = Column(String(200), nullable=False)
    value = Column(Text, nullable=False)
    value_type = Column(String(20), default="string")
    source = Column(String(100), nullable=False)
    last_verified = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("uq_system_knowledge_domain_key", "domain", "key", unique=True),
    )


class Conversation(Base, ActiveRecordMixin):
    """Per-session chat storage."""
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), nullable=False, index=True)
    channel = Column(String(50), nullable=False)
    sender_id = Column(String(200), nullable=False)
    sender_name = Column(String(200), nullable=True)
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    tool_calls = Column(JSON, nullable=True)
    token_count = Column(Integer, nullable=True)
    model = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("idx_conversations_session", "session_id", "created_at"),
        Index("idx_conversations_sender", "sender_id", "created_at"),
    )


class SkillRun(Base, ActiveRecordMixin):
    """Execution log for every skill invocation."""
    __tablename__ = "skill_runs"
    id = Column(Integer, primary_key=True, index=True)
    skill_name = Column(String(100), nullable=False)
    action = Column(String(100), nullable=True)
    triggered_by = Column(String(100), nullable=True)
    input_data = Column(JSON, nullable=True)
    output_data = Column(JSON, nullable=True)
    status = Column(String(20), nullable=False)  # running, success, failed, timeout
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), default=utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)

    __table_args__ = (
        Index("idx_skill_runs_name", "skill_name", "started_at"),
    )


class WorkflowRun(Base, ActiveRecordMixin):
    """Workflow execution state."""
    __tablename__ = "workflow_runs"
    id = Column(Integer, primary_key=True, index=True)
    workflow_name = Column(String(100), nullable=False)
    started_by = Column(String(100), nullable=False)
    channel = Column(String(50), nullable=True)
    status = Column(String(20), nullable=False)  # running, paused, completed, failed, cancelled
    current_step = Column(Integer, default=0)
    state = Column(JSON, nullable=False, default=dict)
    resume_token = Column(Text, nullable=True)
    input_args = Column(JSON, nullable=True)
    output = Column(JSON, nullable=True)
    started_at = Column(DateTime(timezone=True), default=utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    paused_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_workflow_status", "status"),
    )


class AuditLog(Base):
    """Every significant action recorded."""
    __tablename__ = "audit_log"
    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), default=utcnow)
    actor = Column(String(200), nullable=False)
    action = Column(String(100), nullable=False)
    resource = Column(String(200), nullable=True)
    channel = Column(String(50), nullable=True)
    details = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)
    success = Column(Boolean, default=True)

    __table_args__ = (
        Index("idx_audit_timestamp", "timestamp"),
        Index("idx_audit_actor", "actor", "timestamp"),
    )

    @classmethod
    async def log(cls, actor: str, action: str, resource: str = None,
                  channel: str = None, details: dict = None,
                  ip_address: str = None, success: bool = True):
        """Quick helper to write an audit entry."""
        async with AsyncSessionLocal() as session:
            entry = cls(
                actor=actor, action=action, resource=resource,
                channel=channel, details=details,
                ip_address=ip_address, success=success,
            )
            session.add(entry)
            await session.commit()


class LLMUsage(Base):
    """Token and cost tracking per LLM call."""
    __tablename__ = "llm_usage"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), default=utcnow)
    model = Column(String(100), nullable=False)
    provider = Column(String(50), nullable=False)
    tier = Column(Integer, nullable=False)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Float, nullable=True)
    session_id = Column(String(64), nullable=True)
    channel = Column(String(50), nullable=True)
    latency_ms = Column(Integer, nullable=True)

    __table_args__ = (
        Index("idx_llm_usage_date", "timestamp"),
    )


# ==================== DB INIT ====================

async def init_db():
    """Create all tables that don't exist yet."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """Dependency injection for routes that need a session."""
    async with AsyncSessionLocal() as session:
        yield session
