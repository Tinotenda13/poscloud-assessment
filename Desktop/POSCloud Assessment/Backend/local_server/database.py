from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Float, DateTime, func
from datetime import datetime

# Async SQLite engine for local offline storage.
engine = create_async_engine("sqlite+aiosqlite:///./local_pos.db", echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# ORM model for a transaction — stores cashier, amount, description, and sync status.
class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    idempotency_key: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)  # prevents duplicates
    cashier: Mapped[str] = mapped_column(String(100))
    amount: Mapped[float] = mapped_column(Float)
    description: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    sync_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | synced


# ORM model for cashier users — stores username and hashed password.
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)  # stored as plain text for simplicity


# Creates all DB tables on startup if they don't exist.
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# Dependency that provides a DB session per request, then closes it.
async def get_db():
    async with SessionLocal() as session:
        yield session
