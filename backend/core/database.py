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

try:
    from core.config import get_settings
except ImportError:
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

    @classmethod
    async def get_pref(cls, key: str, default=None, domain: str = "preference"):
        """Fetch a system preference by key with type casting."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(cls).where(cls.domain == domain, cls.key == key)
            )
            pref = result.scalars().first()
            if not pref:
                return default
            
            val = pref.value
            vt = (pref.value_type or "string").lower()
            
            if vt == "bool":
                return val.lower() == "true"
            if vt == "int":
                try: return int(val)
                except: return default
            if vt == "float":
                try: return float(val)
                except: return default
            if vt == "list":
                return [v.strip() for v in val.split(",") if v.strip()]
            
            return val

    @classmethod
    async def upsert(
        cls,
        domain: str,
        key: str,
        value,
        value_type: str = "string",
        source: str = "system",
    ):
        """Generic upsert helper for system_knowledge rows."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(cls).where(cls.domain == domain, cls.key == key)
            )
            row = result.scalars().first()
            stored = "" if value is None else str(value)
            if row:
                row.value = stored
                row.value_type = value_type
                row.source = source
                row.updated_at = utcnow()
            else:
                row = cls(
                    domain=domain,
                    key=key,
                    value=stored,
                    value_type=value_type,
                    source=source,
                )
                session.add(row)
            await session.commit()
            return row

    @classmethod
    async def get_by_domain(cls, domain: str) -> list:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(cls).where(cls.domain == domain))
            return list(result.scalars().all())

    @classmethod
    async def set_pref(cls, key: str, value, source: str = "system", domain: str = "preference"):
        """Create or update a system preference."""
        if isinstance(value, bool):
            value_type = "bool"
            stored_value = "true" if value else "false"
        elif isinstance(value, int) and not isinstance(value, bool):
            value_type = "int"
            stored_value = str(value)
        elif isinstance(value, float):
            value_type = "float"
            stored_value = str(value)
        elif isinstance(value, (list, tuple, set)):
            value_type = "list"
            stored_value = ",".join(str(v).strip() for v in value if str(v).strip())
        else:
            value_type = "string"
            stored_value = "" if value is None else str(value)

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(cls).where(cls.domain == domain, cls.key == key)
            )
            pref = result.scalars().first()

            if pref:
                pref.value = stored_value
                pref.value_type = value_type
                pref.source = source
                pref.updated_at = utcnow()
            else:
                pref = cls(
                    domain=domain,
                    key=key,
                    value=stored_value,
                    value_type=value_type,
                    source=source,
                )
                session.add(pref)

            await session.commit()
            return pref

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
                  ip_address: str = None, success: bool = True,
                  detail: str = None):
        """Quick helper to write an audit entry."""
        async with AsyncSessionLocal() as session:
            if details is None and detail is not None:
                details = {"summary": detail}
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


# ==================== INTELLIGENCE BRIEFINGS ====================

class IntelligenceBriefing(Base, ActiveRecordMixin):
    """Daily intelligence briefing with strategic signals."""
    __tablename__ = "intelligence_briefings"
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    html_content = Column(Text, nullable=True)
    pdf_path = Column(String(500), nullable=True)
    metadata_ = Column("metadata", JSON, nullable=True)
    delivered = Column(Boolean, default=False)

    __table_args__ = (
        Index("idx_briefing_created", "created_at"),
    )


class StrategicSignal(Base, ActiveRecordMixin):
    """Individual strategic signal within a briefing."""
    __tablename__ = "strategic_signals"
    id = Column(Integer, primary_key=True, index=True)
    briefing_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    title = Column(String(500), nullable=False)
    link = Column(String(1000), nullable=True)
    source = Column(String(200), nullable=True)
    summary = Column(Text, nullable=True)
    score = Column(Integer, nullable=True)
    classification = Column(String(100), nullable=True)
    business_impact = Column(Text, nullable=True)
    tags = Column(JSON, nullable=True)

    __table_args__ = (
        Index("idx_signal_created", "created_at"),
        Index("idx_signal_score", "score"),
    )


# ==================== SELLER ACCOUNTS ====================

class SellerAccount(Base, ActiveRecordMixin):
    """Soko seller linked to Sanaa Intelligence + WhatsJet."""
    __tablename__ = "seller_accounts"
    id = Column(Integer, primary_key=True, index=True)
    seller_uuid = Column(String(36), unique=True, nullable=False, index=True)
    soko_user_id = Column(Integer, nullable=True)
    name = Column(String(255), nullable=False)
    shop_name = Column(String(255), nullable=True)
    phone = Column(String(20), nullable=True)
    email = Column(String(255), nullable=True)
    whatsjet_vendor_uid = Column(String(100), nullable=True)
    api_key = Column(String(64), unique=True, nullable=False)
    status = Column(String(20), default="active")  # active, suspended
    metadata_ = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("idx_seller_accounts_phone", "phone"),
        Index("idx_seller_accounts_email", "email"),
    )

    @classmethod
    async def get_by_uuid(cls, seller_uuid: str):
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(cls).where(cls.seller_uuid == seller_uuid)
            )
            return result.scalars().first()

    @classmethod
    async def get_by_api_key(cls, api_key: str):
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(cls).where(cls.api_key == api_key)
            )
            return result.scalars().first()


# ==================== DB INIT ====================

async def init_db():
    """Create all tables that don't exist yet."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """Dependency injection for routes that need a session."""
    async with AsyncSessionLocal() as session:
        yield session
