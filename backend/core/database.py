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
    response = Column(Text, nullable=True)
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
    tenant_id = Column(Integer, nullable=True, index=True)  # FK to tenants (nullable for non-tenant alerts)
    acknowledged = Column(Boolean, default=False)
    acknowledged_by = Column(String(100), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("idx_alerts_tenant_id", "tenant_id"),
        Index("idx_alerts_created_at", "created_at"),
    )

    @classmethod
    async def create(cls, **kwargs):
        # Auto-correlate with tenant if tenant_id not explicitly provided
        if "tenant_id" not in kwargs or kwargs["tenant_id"] is None:
            try:
                tenant_id = await cls._correlate_tenant(kwargs)
                if tenant_id:
                    kwargs["tenant_id"] = tenant_id
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Alert tenant correlation failed: {e}")

        # Call the mixin's create
        instance = await super().create(**kwargs)
        
        # Trigger instant notification
        severity = kwargs.get("severity", "info").lower()
        if severity in ("high", "critical"):
            try:
                import asyncio
                from core.agents.report_agent import ReportAgent
                reporter = ReportAgent()
                subject = f"[Sanaa AI] {severity.upper()} ALERT: {kwargs.get('title', kwargs.get('source', 'System'))}"
                body = f"Severity: {severity.upper()}\nSource: {kwargs.get('source', 'N/A')}\nMetric: {kwargs.get('metric', 'N/A')}\n\n{kwargs.get('message', '')}"
                
                # Check for active event loop before creating task
                try:
                    asyncio.get_running_loop()
                    asyncio.create_task(reporter.send_alert_email(subject, body))
                except RuntimeError:
                    asyncio.create_task(reporter.send_alert_email(subject, body))
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Failed to trigger instant alert notification: {e}")
                
        return instance

    @classmethod
    async def _correlate_tenant(cls, kwargs: dict) -> int | None:
        """Try to match an alert to a tenant by source, title, message, or URL patterns.

        Matching strategy:
        1. Exact tenant_id if provided
        2. Match source/title/message against tenant name
        3. Match source/title/message against tenant URL
        """
        source = (kwargs.get("source") or "").lower()
        title = (kwargs.get("title") or "").lower()
        message = (kwargs.get("message") or "").lower()
        search_text = f"{source} {title} {message}"

        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Tenant))
            tenants = result.scalars().all()

            for tenant in tenants:
                tenant_name = (tenant.name or "").lower()
                tenant_url = (tenant.url or "").lower()

                # Match by tenant name in the alert text
                if tenant_name and tenant_name in search_text:
                    return tenant.id

                # Match by tenant URL (or domain portion) in the alert text
                if tenant_url:
                    # Extract domain from URL for matching
                    from urllib.parse import urlparse
                    try:
                        parsed = urlparse(tenant_url)
                        domain = parsed.hostname or ""
                        if domain and domain in search_text:
                            return tenant.id
                    except Exception:
                        pass

        return None

    @classmethod
    async def get_by_tenant(cls, tenant_id: int, limit: int = 20):
        """Get recent alerts for a specific tenant, ordered by most recent first."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(cls)
                .where(cls.tenant_id == tenant_id)
                .order_by(desc(cls.created_at))
                .limit(limit)
            )
            return result.scalars().all()


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
        """Fetch a system preference by key with type casting.

        Sensitive keys (e.g. brain.api_key.*) are automatically decrypted.
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(cls).where(cls.domain == domain, cls.key == key)
            )
            pref = result.scalars().first()
            if not pref:
                return default
            
            val = pref.value
            vt = (pref.value_type or "string").lower()

            # Transparently decrypt sensitive values
            try:
                from core.utils.crypto import is_sensitive_key, maybe_decrypt
                if is_sensitive_key(key):
                    val = maybe_decrypt(val)
            except Exception:
                pass  # Graceful degradation — return raw value if crypto fails
            
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
        """Generic upsert helper for system_knowledge rows.

        Sensitive keys are automatically encrypted before storage.
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(cls).where(cls.domain == domain, cls.key == key)
            )
            row = result.scalars().first()
            stored = "" if value is None else str(value)

            # Transparently encrypt sensitive values before storing
            try:
                from core.utils.crypto import is_sensitive_key, encrypt_value, is_encrypted
                if is_sensitive_key(key) and stored and not is_encrypted(stored):
                    stored = encrypt_value(stored)
            except Exception:
                pass  # Graceful degradation

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
        """Create or update a system preference.

        Sensitive keys (e.g. brain.api_key.*) are automatically encrypted before storage.
        """
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

        # Transparently encrypt sensitive values before storing
        try:
            from core.utils.crypto import is_sensitive_key, encrypt_value, is_encrypted
            if is_sensitive_key(key) and stored_value and not is_encrypted(stored_value):
                stored_value = encrypt_value(stored_value)
        except Exception:
            pass  # Graceful degradation — store plaintext if crypto fails

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

    @classmethod
    async def get_since(cls, since_dt):
        """Get LLM usage records since a given datetime."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(cls).where(cls.timestamp >= since_dt).order_by(cls.timestamp.desc())
            )
            return result.scalars().all()


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


class PendingApproval(Base, ActiveRecordMixin):
    """Token-based approval queue for destructive operations."""
    __tablename__ = "pending_approvals"
    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(255), nullable=False)
    target = Column(String(255), nullable=False)
    details = Column(JSON, nullable=True)
    requested_at = Column(DateTime(timezone=True), default=utcnow)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_via = Column(String(50), nullable=True)  # whatsapp, email, dashboard
    token = Column(String(255), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("idx_pending_approvals_token", "token"),
    )


# ==================== ML SELF-LEARNING TABLES ====================

class SkillMetrics(Base, ActiveRecordMixin):
    """Per-skill performance metrics aggregated from skill_runs for ML analysis."""
    __tablename__ = "skill_metrics"
    id = Column(Integer, primary_key=True, index=True)
    skill_name = Column(String(100), nullable=False, index=True)
    period = Column(String(20), nullable=False)  # hourly, daily, weekly
    period_start = Column(DateTime(timezone=True), nullable=False)
    total_runs = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)
    timeout_count = Column(Integer, default=0)
    avg_duration_ms = Column(Float, default=0)
    p95_duration_ms = Column(Float, default=0)
    success_rate = Column(Float, default=0)
    avg_user_rating = Column(Float, nullable=True)
    rating_count = Column(Integer, default=0)
    error_categories = Column(JSON, nullable=True)
    performance_score = Column(Float, default=0.5)  # 0-1 composite ML score
    trend = Column(String(20), default="stable")  # improving, degrading, stable
    created_at = Column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("idx_skill_metrics_name_period", "skill_name", "period", "period_start"),
        Index("idx_skill_metrics_score", "performance_score"),
    )

    @classmethod
    async def get_latest(cls, skill_name: str, period: str = "daily"):
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(cls)
                .where(cls.skill_name == skill_name, cls.period == period)
                .order_by(desc(cls.period_start))
                .limit(1)
            )
            return result.scalars().first()

    @classmethod
    async def get_history(cls, skill_name: str, period: str = "daily", limit: int = 30):
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(cls)
                .where(cls.skill_name == skill_name, cls.period == period)
                .order_by(desc(cls.period_start))
                .limit(limit)
            )
            return list(result.scalars().all())

    @classmethod
    async def get_all_latest(cls, period: str = "daily"):
        """Get the most recent metrics for all skills."""
        async with AsyncSessionLocal() as session:
            subq = (
                select(cls.skill_name, func.max(cls.period_start).label("max_start"))
                .where(cls.period == period)
                .group_by(cls.skill_name)
                .subquery()
            )
            result = await session.execute(
                select(cls).join(
                    subq,
                    (cls.skill_name == subq.c.skill_name)
                    & (cls.period_start == subq.c.max_start)
                    & (cls.period == period)
                )
            )
            return list(result.scalars().all())


class SkillFeedback(Base, ActiveRecordMixin):
    """User feedback on skill execution results for supervised learning."""
    __tablename__ = "skill_feedback"
    id = Column(Integer, primary_key=True, index=True)
    skill_run_id = Column(Integer, nullable=True)
    skill_name = Column(String(100), nullable=False, index=True)
    rating = Column(Integer, nullable=False)  # 1-5 stars or -1/0/1 (thumbs)
    feedback_type = Column(String(20), default="thumbs")  # thumbs, stars, text
    comment = Column(Text, nullable=True)
    session_id = Column(String(64), nullable=True)
    input_args = Column(JSON, nullable=True)
    output_snapshot = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("idx_skill_feedback_name", "skill_name", "created_at"),
    )


class SkillLearningLog(Base, ActiveRecordMixin):
    """Tracks ML model training events and what the system has learned about each skill."""
    __tablename__ = "skill_learning_log"
    id = Column(Integer, primary_key=True, index=True)
    skill_name = Column(String(100), nullable=False, index=True)
    event_type = Column(String(50), nullable=False)  # parameter_tuned, pattern_found, anomaly_detected, improvement_applied, performance_shift
    description = Column(Text, nullable=False)
    old_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=True)
    confidence = Column(Float, default=0.5)
    impact = Column(String(20), default="low")  # low, medium, high
    applied = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("idx_skill_learning_name", "skill_name", "created_at"),
        Index("idx_skill_learning_type", "event_type"),
    )

    @classmethod
    async def get_recent(cls, skill_name: str = None, limit: int = 20):
        async with AsyncSessionLocal() as session:
            q = select(cls).order_by(desc(cls.created_at)).limit(limit)
            if skill_name:
                q = q.where(cls.skill_name == skill_name)
            result = await session.execute(q)
            return list(result.scalars().all())


class SkillParameterProfile(Base, ActiveRecordMixin):
    """Learned optimal parameter configurations per skill based on successful runs."""
    __tablename__ = "skill_parameter_profiles"
    id = Column(Integer, primary_key=True, index=True)
    skill_name = Column(String(100), nullable=False, index=True)
    parameter_name = Column(String(100), nullable=False)
    optimal_value = Column(Text, nullable=True)
    value_distribution = Column(JSON, nullable=True)  # {"value1": count, "value2": count}
    success_correlation = Column(Float, default=0)  # -1 to 1
    sample_size = Column(Integer, default=0)
    last_updated = Column(DateTime(timezone=True), default=utcnow)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("idx_skill_param_profile", "skill_name", "parameter_name", unique=True),
    )


# ==================== LEARNING LOGS ====================

class LearningLog(Base, ActiveRecordMixin):
    """OpenClaw-inspired structured learning log entries.

    Three log types: LEARNINGS (insights/facts), ERRORS (mistakes/failures),
    FEATURE_REQUESTS (user suggestions). Entries can be promoted to system
    context when patterns are detected repeatedly.
    """
    __tablename__ = "learning_logs"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    log_type = Column(String(30), nullable=False, index=True)  # LEARNINGS, ERRORS, FEATURE_REQUESTS
    source = Column(String(30), nullable=False)  # conversation, reflection, error, user
    content = Column(Text, nullable=False)
    confidence = Column(Float, default=0.5, nullable=False)
    category = Column(String(100), nullable=False, index=True)
    promoted = Column(Boolean, default=False, nullable=False)
    promotion_timestamp = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_learning_logs_type_ts", "log_type", "timestamp"),
        Index("idx_learning_logs_category", "category"),
        Index("idx_learning_logs_promoted", "promoted"),
    )


# ==================== SCHEDULED POSTS ====================

class ScheduledPost(Base, ActiveRecordMixin):
    """Scheduled social media posts for multi-platform publishing."""
    __tablename__ = "scheduled_posts"
    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String(50), nullable=False, index=True)  # twitter, linkedin, facebook
    content = Column(Text, nullable=False)
    scheduled_time = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(20), default="scheduled", nullable=False)  # scheduled, published, failed, cancelled
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("idx_scheduled_posts_platform", "platform"),
        Index("idx_scheduled_posts_status", "status"),
        Index("idx_scheduled_posts_time", "scheduled_time"),
    )


# ==================== EMAIL CAMPAIGNS ====================

class AudienceSegment(Base, ActiveRecordMixin):
    """Reusable audience segment definitions for email marketing."""
    __tablename__ = "audience_segments"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    criteria = Column(JSON, nullable=False)  # e.g. {"role": "admin", "region": "East Africa"}
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("idx_audience_segments_name", "name"),
    )


class EmailCampaign(Base, ActiveRecordMixin):
    """Email marketing campaigns with subject, body template, and segment."""
    __tablename__ = "email_campaigns"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(300), nullable=False)
    subject = Column(String(500), nullable=False)
    body_template = Column(Text, nullable=False)
    segment_id = Column(Integer, nullable=True)  # FK to audience_segments
    status = Column(String(20), default="draft", nullable=False)  # draft, sending, sent, failed
    recipients_count = Column(Integer, default=0)
    sent_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("idx_email_campaigns_status", "status"),
        Index("idx_email_campaigns_created", "created_at"),
    )


# ==================== CALENDAR / TASK MANAGEMENT ====================

class TaskCalendar(Base, ActiveRecordMixin):
    """Calendar task with due date, priority, status, and reminders."""
    __tablename__ = "tasks_calendar"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    due_date = Column(DateTime(timezone=True), nullable=True)
    priority = Column(String(20), default="medium", nullable=False)  # low, medium, high, urgent
    status = Column(String(20), default="pending", nullable=False)  # pending, in_progress, done, cancelled
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("idx_tasks_calendar_status", "status"),
        Index("idx_tasks_calendar_priority", "priority"),
        Index("idx_tasks_calendar_due_date", "due_date"),
    )


class TaskReminder(Base, ActiveRecordMixin):
    """Reminder entry associated with a calendar task."""
    __tablename__ = "task_reminders"
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, nullable=False, index=True)
    trigger_time = Column(DateTime(timezone=True), nullable=False)
    message = Column(Text, nullable=True)
    triggered = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("idx_task_reminders_task", "task_id"),
        Index("idx_task_reminders_trigger", "trigger_time", "triggered"),
    )


# ==================== TENANT CONTROL ====================

class Tenant(Base, ActiveRecordMixin):
    """Unified tenant data model for all managed services.

    Represents finance tenants, e-commerce (Soko), email (Mailcow), and
    other services as first-class entities in the control plane.
    """
    __tablename__ = "tenants"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, unique=True)
    type = Column(String(20), nullable=False)  # finance, ecommerce, email, other
    url = Column(String(500), nullable=True)
    status = Column(String(20), default="active", nullable=False)  # active, inactive, degraded, down
    health_score = Column(Float, default=100.0, nullable=False)
    last_checked = Column(DateTime(timezone=True), nullable=True)
    config = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("idx_tenants_name", "name", unique=True),
        Index("idx_tenants_type", "type"),
        Index("idx_tenants_status", "status"),
    )


# ==================== ALERT RULES ====================

class AlertRule(Base, ActiveRecordMixin):
    """Configurable alert rules with routing, escalation, and quiet hours.

    Each rule defines: what to watch (condition/threshold), who to notify
    (recipients), how to escalate (escalation_policy), and when to suppress
    (quiet_hours).
    """
    __tablename__ = "alert_rules"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    condition = Column(String(500), nullable=False)      # metric name or expression
    threshold = Column(Float, nullable=False)             # trigger when value > threshold
    severity = Column(String(20), nullable=False)         # low, medium, high, critical
    recipients = Column(JSON, nullable=False)             # list of email addresses
    escalation_policy = Column(JSON, nullable=True)       # {"levels": [{"channel": "email", "timeout_minutes": 0}, ...]}
    quiet_hours = Column(JSON, nullable=True)             # {"start": "22:00", "end": "07:00", "timezone": "Africa/Kampala"}
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        Index("idx_alert_rules_condition", "condition"),
        Index("idx_alert_rules_severity", "severity"),
        Index("idx_alert_rules_enabled", "enabled"),
    )


class AlertEscalation(Base, ActiveRecordMixin):
    """Tracks active escalation state for triggered alerts.

    Records the current escalation level and timestamps so the
    EscalationEngine knows when to advance to the next tier.
    """
    __tablename__ = "alert_escalations"
    id = Column(Integer, primary_key=True, index=True)
    alert_rule_id = Column(Integer, nullable=False, index=True)
    message = Column(Text, nullable=False)
    recipients = Column(JSON, nullable=False)
    policy = Column(JSON, nullable=False)
    current_level = Column(Integer, default=0, nullable=False)
    acknowledged = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    last_escalated_at = Column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("idx_alert_escalations_rule", "alert_rule_id"),
        Index("idx_alert_escalations_ack", "acknowledged"),
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
