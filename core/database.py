import os
import json
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON, select, desc

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://antigravity:CHANGE_THIS_STRONG_PASSWORD@localhost:5432/antigravity_db")
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

# Helper mixin to match the blueprint's Active Record style usage
class ActiveRecordMixin:
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
            result = await session.execute(select(cls).order_by(desc(cls.created_at)).limit(limit))
            return result.scalars().all()

    async def update(self, **kwargs):
        async with AsyncSessionLocal() as session:
            # Re-fetch to ensure attached to session
            instance = await session.get(self.__class__, self.id)
            for key, value in kwargs.items():
                setattr(instance, key, value)
            await session.commit()
            await session.refresh(instance)
            # Update self
            for key, value in kwargs.items():
                setattr(self, key, value)
            return self

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

class Log(Base, ActiveRecordMixin):
    __tablename__ = "logs"
    id = Column(Integer, primary_key=True, index=True)
    source = Column(String)
    level = Column(String)
    message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

class Command(Base, ActiveRecordMixin):
    __tablename__ = "commands"
    id = Column(Integer, primary_key=True, index=True) # Blueprint uses string ID in one place, let's use Int with str conversion or UUID. Blueprint implies UUID? "cmd.id". Let's use string UUID.
    # Actually, let's use String ID for UUID compatibility
    id = Column(String, primary_key=True, default=lambda: str(os.urandom(4).hex())) 
    text = Column(String)
    context = Column(String, nullable=True)
    status = Column(String) # analyzing, awaiting_approval, executing, completed, rejected
    proposed_plan = Column(JSON, nullable=True)
    results = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class DeviceReport(Base, ActiveRecordMixin):
    __tablename__ = "device_reports"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, index=True)
    device_name = Column(String)
    data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

    @classmethod
    async def get_latest_all(cls):
        # Naive implementation: get all recent and dedupe by device_id in python
        # Better: proper SQL group by. For now, simple.
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(cls).order_by(desc(cls.created_at)).limit(50))
            reports = result.scalars().all()
            latest = {}
            for r in reports:
                if r.device_id not in latest:
                    latest[r.device_id] = r
            return list(latest.values())

class Alert(Base, ActiveRecordMixin):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True, index=True)
    severity = Column(String)
    message = Column(String)
    metric = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
