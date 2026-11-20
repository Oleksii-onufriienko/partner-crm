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

-- История ступеней: старт и каждое повышение/перевод с датой
CREATE TABLE IF NOT EXISTS stufe_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id   INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    stufe       TEXT NOT NULL,
    date        TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'promotion',     -- start | promotion | change
    created_by  INTEGER,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_stufe_history_person ON stufe_history(person_id, date);

-- Журнал этапов воронки партнёров (когда кандидат перешёл на этап)
CREATE TABLE IF NOT EXISTS recruit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id  INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    stage       TEXT NOT NULL,
    date        TEXT NOT NULL,
    created_by  INTEGER,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_recruit_log_contact ON recruit_log(contact_id);

-- Годовой план (Jahresplanung): цели по месяцам
CREATE TABLE IF NOT EXISTS year_goals (
    person_id   INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    year        INTEGER NOT NULL,
    month       INTEGER NOT NULL,
    metric      TEXT NOT NULL,
    ziel        REAL,
    updated_by  INTEGER,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (person_id, year, month, metric)
);

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
    ("contacts", "recruit_stage", "TEXT"),        # этап воронки партнёров
    ("contacts", "recruit_info_date", "TEXT"),    # дата Karriere-Info
    ("contacts", "joined_person_id", "INTEGER"),  # кем стал в структуре
]

# Перенос данных (каждый раз безопасно): старые коды ступеней, стартовая история ступеней,
# кандидаты из старой галочки «интерес к партнёрству».
DATA_MIGRATIONS = [
    "UPDATE persons SET stufe = 'VBAK' WHERE stufe = 'VBA'",
    "UPDATE persons SET stufe = 'RD1' WHERE stufe = 'RD'",
    "UPDATE stufe_history SET stufe = 'VBAK' WHERE stufe = 'VBA'",
    "UPDATE stufe_history SET stufe = 'RD1' WHERE stufe = 'RD'",
    """INSERT INTO stufe_history (person_id, stufe, date, kind)
       SELECT id, stufe, COALESCE(start_date, date(created_at)), 'start' FROM persons p
       WHERE NOT EXISTS (SELECT 1 FROM stufe_history h WHERE h.person_id = p.id)""",
    "UPDATE contacts SET recruit_stage = 'interest' WHERE partner_interest = 1 AND recruit_stage IS NULL",
    """INSERT INTO recruit_log (contact_id, stage, date)
       SELECT id, recruit_stage, date(updated_at) FROM contacts c
       WHERE recruit_stage IS NOT NULL AND NOT EXISTS (SELECT 1 FROM recruit_log l WHERE l.contact_id = c.id)""",
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
    for sql in DATA_MIGRATIONS:
        db.execute(sql)
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
