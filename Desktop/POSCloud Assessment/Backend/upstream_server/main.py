from fastapi import FastAPI, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from contextlib import asynccontextmanager
from database import init_db, get_db, Transaction
from schemas import TransactionIngest, TransactionResponse


# On startup: init the PostgreSQL DB tables. No scheduler needed — upstream is always online.
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="POS Upstream Server", lifespan=lifespan)

# Receives a transaction from the local server. Saves it to PostgreSQL.
# Returns 409 if already exists (idempotent) so local server can mark it as synced.
@app.post("/transactions", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def ingest_transaction(payload: TransactionIngest, db: AsyncSession = Depends(get_db)):
    txn = Transaction(
        idempotency_key=payload.idempotency_key,
        cashier=payload.cashier,
        amount=payload.amount,
        description=payload.description,
        created_at=payload.created_at,
    )
    db.add(txn)
    try:
        await db.commit()
        await db.refresh(txn)
        return txn
    except IntegrityError:
        await db.rollback()
        # Already exists — idempotent: return 409 so local server marks it synced
        result = await db.execute(
            select(Transaction).where(Transaction.idempotency_key == payload.idempotency_key)
        )
        existing = result.scalar_one()
        return JSONResponse(status_code=409, content={"detail": "Already exists", "idempotency_key": existing.idempotency_key})

# Returns all transactions from PostgreSQL, newest first.
@app.get("/transactions", response_model=list[TransactionResponse])
async def list_transactions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Transaction).order_by(Transaction.created_at.desc()))
    return result.scalars().all()
