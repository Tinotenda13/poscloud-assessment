-- Run as a superuser: psql -U postgres -f init_db.sql

CREATE DATABASE poscloud;

\c poscloud

CREATE TABLE IF NOT EXISTS transactions (
    id              SERIAL PRIMARY KEY,
    idempotency_key VARCHAR(36)    NOT NULL,
    cashier         VARCHAR(100)   NOT NULL,
    amount          FLOAT          NOT NULL,
    description     VARCHAR(255)   NOT NULL,
    created_at      TIMESTAMP      NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_idempotency_key UNIQUE (idempotency_key)
);
