import httpx
import logging
from sqlalchemy import select, update
from database import SessionLocal, Transaction

logger = logging.getLogger(__name__)
UPSTREAM_URL = None  # injected from main


async def is_online() -> bool:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.get("https://www.google.com")
        return True
    except httpx.RequestError:
        return False


async def sync_pending_transactions():
    if not await is_online():
        logger.warning("No internet connection, skipping sync.")
        return
    async with SessionLocal() as db:
        result = await db.execute(
            select(Transaction).where(Transaction.sync_status == "pending")
        )
        pending = result.scalars().all()

        if not pending:
            return

        async with httpx.AsyncClient(timeout=5.0) as client:
            for txn in pending:
                try:
                    resp = await client.post(
                        f"{UPSTREAM_URL}/transactions",
                        json={
                            "idempotency_key": txn.idempotency_key,
                            "cashier": txn.cashier,
                            "amount": txn.amount,
                            "description": txn.description,
                            "created_at": txn.created_at.isoformat(),
                        },
                    )
                    # 200 OK or 409 Conflict (already exists) both mean success
                    if resp.status_code in (200, 201, 409):
                        await db.execute(
                            update(Transaction)
                            .where(Transaction.id == txn.id)
                            .values(sync_status="synced")
                        )
                        await db.commit()
                        logger.info(f"Synced transaction {txn.idempotency_key}")
                    else:
                        logger.warning(f"Upstream rejected {txn.idempotency_key}: {resp.status_code}")
                except httpx.RequestError as e:
                    logger.warning(f"Upstream unreachable, will retry later: {e}")
                    break  # stop trying; scheduler will retry
