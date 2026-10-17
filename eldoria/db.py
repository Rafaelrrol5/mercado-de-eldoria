import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import click
from flask import current_app, g


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE CHECK(email = lower(email)),
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'CUSTOMER' CHECK(role IN ('CUSTOMER', 'ADMIN')),
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE', 'SUSPENDED', 'DISABLED')),
    game_identifier TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS support_tickets (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    order_number TEXT,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    category TEXT NOT NULL,
    subject TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    number TEXT NOT NULL UNIQUE,
    user_id TEXT NOT NULL REFERENCES users(id),
    game_identifier TEXT NOT NULL,
    subtotal_cents INTEGER NOT NULL CHECK(subtotal_cents >= 0),
    total_cents INTEGER NOT NULL CHECK(total_cents >= 0),
    status TEXT NOT NULL DEFAULT 'AWAITING_PAYMENT',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS order_items (
    id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_slug TEXT NOT NULL,
    product_name TEXT NOT NULL,
    unit_price_cents INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity > 0)
);
CREATE INDEX IF NOT EXISTS idx_tickets_user ON support_tickets(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id, created_at);
CREATE TABLE IF NOT EXISTS catalog_products (slug TEXT PRIMARY KEY, data TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS site_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ticket_messages (
    id TEXT PRIMARY KEY, ticket_id TEXT NOT NULL REFERENCES support_tickets(id),
    author_id TEXT NOT NULL REFERENCES users(id), body TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_ticket ON ticket_messages(ticket_id, created_at);
CREATE TABLE IF NOT EXISTS order_management (
    order_id TEXT PRIMARY KEY REFERENCES orders(id), payment TEXT NOT NULL DEFAULT 'PENDING',
    delivery TEXT NOT NULL DEFAULT 'PENDING', note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS admin_events (
    id TEXT PRIMARY KEY, admin_id TEXT NOT NULL REFERENCES users(id), action TEXT NOT NULL,
    target TEXT NOT NULL, details TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS financial_events (
    order_id TEXT NOT NULL REFERENCES orders(id), kind TEXT NOT NULL CHECK(kind IN ('PAYMENT','REFUND')),
    amount_cents INTEGER NOT NULL CHECK(amount_cents >= 0), occurred_at TEXT NOT NULL,
    inferred INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(order_id, kind)
);
CREATE INDEX IF NOT EXISTS idx_financial_date ON financial_events(occurred_at);
CREATE TABLE IF NOT EXISTS user_security (
    user_id TEXT PRIMARY KEY REFERENCES users(id), email_verified_at TEXT,
    session_version INTEGER NOT NULL DEFAULT 0, totp_secret TEXT, totp_pending TEXT,
    pending_expires INTEGER, totp_last_step INTEGER NOT NULL DEFAULT -1,
    recovery_codes TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS account_tokens (
    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
    purpose TEXT NOT NULL CHECK(purpose IN ('verify','reset')), expires_at INTEGER NOT NULL,
    used_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_account_tokens_user ON account_tokens(user_id,purpose);
CREATE TABLE IF NOT EXISTS auth_throttle (
    bucket TEXT PRIMARY KEY, attempts INTEGER NOT NULL, expires_at INTEGER NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_normalized_email ON users(lower(trim(email)));
"""


def get_db():
    if "db" not in g:
        path = Path(current_app.config["DATABASE"])
        path.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(path)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    get_db().executescript(SCHEMA)
    from .products import seed_catalog
    seed_catalog()
    # Existing paid orders have no payment timestamp. Preserve them and flag the estimated date.
    get_db().execute("""INSERT OR IGNORE INTO financial_events
        SELECT id, 'PAYMENT', total_cents, created_at, 1 FROM orders
        WHERE status IN ('PAID','PROCESSING','DELIVERED','REFUNDED')""")
    get_db().execute("""INSERT OR IGNORE INTO financial_events
        SELECT id, 'REFUND', total_cents, created_at, 1 FROM orders WHERE status='REFUNDED'""")
    get_db().commit()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


@click.command("init-db")
def init_db_command():
    init_db()
    click.echo("Banco de dados inicializado.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    with app.app_context():
        init_db()

