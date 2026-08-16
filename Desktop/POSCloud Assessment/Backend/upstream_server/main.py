from fastapi import FastAPI, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from contextlib import asynccontextmanager
from database import init_db, get_db, Transaction
from schemas import TransactionIngest, TransactionResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="POS Upstream Server", lifespan=lifespan)

# Create a transaction endpoint that accepts a POST request with a JSON payload containing the transaction details. The endpoint should validate the payload, create a new transaction record in the database, and return a response indicating success or failure. If the transaction already exists (based on the idempotency key), it should return a 409 Conflict response.  
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

# List transactions endpoint that accepts a GET request and returns a list of all transactions in the database, ordered by creation date (most recent first). The response should include the transaction details in JSON format.
@app.get("/transactions", response_model=list[TransactionResponse])
async def list_transactions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Transaction).order_by(Transaction.created_at.desc()))
    return result.scalars().all()
