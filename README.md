# POSCloud – Offline Retail Transaction System

## Architecture

```
[Cashier / POS Device]
        │
        ▼
 local_server  (FastAPI + SQLite)   ← always available, offline-first
        │  background sync every 10s
        ▼
upstream_server (FastAPI + MySQL)   ← central server
```

- The **local server** runs on the POS device. Transactions are always written to SQLite first.
- A background scheduler retries syncing `pending` transactions to the upstream every 10 seconds.
- The **upstream server** enforces a `UNIQUE` constraint on `idempotency_key` — duplicate pushes return `409` and are safely ignored.
- Both `200/201` and `409` from upstream cause the local record to be marked `synced`.
- If connectivity drops mid-sync, the scheduler picks up remaining `pending` records on the next run.

---

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure environment
Edit `.env`:
```
POSTGRES_URL=postgresql+asyncpg://<user>:<password>@localhost:5432/poscloud
UPSTREAM_URL=http://localhost:8001
```

### 3. Initialize PostgreSQL
```bash
psql -U postgres -f init_db.sql
```

### 4. Run upstream server (port 8001)
```bash
cd upstream_server
uvicorn main:app --port 8001 --reload
```

### 5. Run local server (port 8000)
```bash
cd local_server
uvicorn main:app --port 8000 --reload
```

---

## API Reference

### Local Server (`http://localhost:8000`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/transactions` | Create a new transaction |
| `GET`  | `/transactions` | List all transactions (with sync status) |
| `GET`  | `/transactions/{idempotency_key}` | Get a single transaction |
| `POST` | `/sync/trigger` | Manually trigger sync |

#### POST /transactions – Request Body
```json
{
  "cashier": "Jane",
  "amount": 49.99,
  "description": "Groceries",
  "idempotency_key": "550e8400-e29b-41d4-a716-446655440000"  // optional, auto-generated if omitted
}
```

#### Transaction Response
```json
{
  "id": 1,
  "idempotency_key": "550e8400-e29b-41d4-a716-446655440000",
  "cashier": "Jane",
  "amount": 49.99,
  "description": "Groceries",
  "created_at": "2024-01-15T10:30:00",
  "sync_status": "pending"   // or "synced"
}
```

### Upstream Server (`http://localhost:8001`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/transactions` | Ingest a transaction (idempotent) |
| `GET`  | `/transactions` | List all synced transactions |

---

## Key Design Decisions

| Concern | Solution |
|---------|----------|
| Offline persistence | SQLite on device — survives restarts |
| Duplicate prevention | `idempotency_key` (UUID) with `UNIQUE` constraint on both DBs |
| Sync retry | APScheduler polls every 10s; stops on first network error, resumes next cycle |
| Mid-sync crash recovery | Only marks `synced` after confirmed upstream `2xx` or `409` |
| Connectivity loss mid-sync | Remaining `pending` rows are retried on next scheduler tick |
