import sqlite3

import click
from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS persons (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id       INTEGER REFERENCES persons(id) ON DELETE RESTRICT,  -- наставник (бетроер выше)
    first_name      TEXT NOT NULL,
    last_name       TEXT NOT NULL,
    stufe           TEXT NOT NULL DEFAULT 'VM',
    coef            REAL,                       -- € за 1 KE
    birth_date      TEXT,
    phone           TEXT,
    email           TEXT,                       -- логин (в нижнем регистре)
    start_date      TEXT,                       -- дата входа в бизнес
    goal_ke_month   REAL,                       -- цель KE в месяц
    note            TEXT,
    is_admin        INTEGER NOT NULL DEFAULT 0,
    password_hash   TEXT,                       -- NULL = кабинета ещё нет
    invite_hash     TEXT,                       -- sha256 токена приглашения
    invite_expires  TEXT,
    active          INTEGER NOT NULL DEFAULT 1,
    last_login      TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    created_by      INTEGER
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_persons_email ON persons(email) WHERE email IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_persons_parent ON persons(parent_id);

-- Marktpotenzial: контакты партнёра
CREATE TABLE IF NOT EXISTS contacts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id         INTEGER NOT NULL REFERENCES persons(id) ON DELETE RESTRICT,
    first_name       TEXT NOT NULL,
    last_name        TEXT,
    phone            TEXT,
    email            TEXT,
    age              INTEGER,
    profession       TEXT,
    channel          TEXT NOT NULL DEFAULT 'warm',
    recommended_by   TEXT,
    temperature      TEXT NOT NULL DEFAULT 'warm',
    kind             TEXT NOT NULL DEFAULT 'prospect',
    status           TEXT NOT NULL DEFAULT 'new',
    partner_interest INTEGER NOT NULL DEFAULT 0,
    next_action      TEXT,
    next_action_date TEXT,
    comment          TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_contacts_owner ON contacts(owner_id);

-- Потенциальные сделки (что может быть интересно человеку)
CREATE TABLE IF NOT EXISTS potentials (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id  INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    product     TEXT NOT NULL,
    ke          REAL NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_potentials_contact ON potentials(contact_id);

-- Оформленные сделки
CREATE TABLE IF NOT EXISTS deals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id  INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    date        TEXT NOT NULL,
    product     TEXT NOT NULL,
    ke          REAL NOT NULL DEFAULT 0,
    note        TEXT,
    source      TEXT NOT NULL DEFAULT 'consult',     -- consult = бератунг, service = сервис-термин
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_deals_contact ON deals(contact_id);
CREATE INDEX IF NOT EXISTS ix_deals_date ON deals(date);

-- Встречи / термины
CREATE TABLE IF NOT EXISTS meetings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id     INTEGER NOT NULL REFERENCES persons(id) ON DELETE RESTRICT,
    contact_id   INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
    title        TEXT,
    date         TEXT NOT NULL,
    time         TEXT,
    duration_min INTEGER,
    format       TEXT NOT NULL DEFAULT 'offline',
    stage        TEXT NOT NULL DEFAULT 'first',
    status       TEXT NOT NULL DEFAULT 'planned',
    expected_ke  REAL,
    note         TEXT,
    created_by   INTEGER REFERENCES persons(id),
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_meetings_owner_date ON meetings(owner_id, date);
CREATE INDEX IF NOT EXISTS ix_meetings_contact ON meetings(contact_id);

-- План (Soll) и ручной факт (Ist) по неделям. week = понедельник недели.
-- ist = NULL: для автоматических показателей факт считается из встреч и сделок.
CREATE TABLE IF NOT EXISTS week_plan (
    person_id   INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    week        TEXT NOT NULL,
    metric      TEXT NOT NULL,
    soll        REAL,
    ist         REAL,
    updated_by  INTEGER,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (person_id, week, metric)
);
"""

# Изменения схемы для уже существующих баз: (таблица, колонка, определение)
MIGRATIONS = [
    ("deals", "source", "TEXT NOT NULL DEFAULT 'consult'"),
    ("persons", "prefs", "TEXT"),          # личные настройки пользователя (JSON)
]


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    return (rows[0] if rows else None) if one else rows


def execute(sql, args=()):
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    return cur.lastrowid


def init_db():
    db = get_db()
    db.execute("PRAGMA journal_mode = WAL")
    db.executescript(SCHEMA)
    for table, column, definition in MIGRATIONS:
        cols = [r[1] for r in db.execute(f"PRAGMA table_info({table})")]
        if column not in cols:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    db.commit()


@click.command("init-db")
def init_db_command():
    """Создать таблицы (безопасно запускать повторно)."""
    init_db()
    click.echo("База данных готова.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    with app.app_context():
        init_db()
