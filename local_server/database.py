from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Float, DateTime, func
from datetime import datetime

engine = create_async_engine("sqlite+aiosqlite:///./local_pos.db", echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    idempotency_key: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    cashier: Mapped[str] = mapped_column(String(100))
    amount: Mapped[float] = mapped_column(Float)
    description: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    sync_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | synced


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    async with SessionLocal() as session:
        yield session
