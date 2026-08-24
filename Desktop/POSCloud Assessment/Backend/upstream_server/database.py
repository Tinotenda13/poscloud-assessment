from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Float, DateTime, func
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv(dotenv_path="../.env")

POSTGRES_URL = os.getenv("UPSTREAM_POSTGRES_URL", "postgresql+asyncpg://postgres:Tinotenda@localhost:5432/poscloud_upstream")

# Async PostgreSQL engine for the upstream cloud database.
engine = create_async_engine(POSTGRES_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# ORM model for upstream transactions — same structure as local but no sync_status (already the source of truth).
class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    idempotency_key: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)  # prevents duplicates
    cashier: Mapped[str] = mapped_column(String(100))
    amount: Mapped[float] = mapped_column(Float)
    description: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


# Creates all DB tables on startup if they don't exist.
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# Dependency that provides a DB session per request, then closes it.
async def get_db():
    async with SessionLocal() as session:
        yield session
