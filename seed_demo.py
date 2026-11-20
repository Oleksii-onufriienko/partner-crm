"""Демо-данные, чтобы посмотреть систему «в деле».

    python seed_demo.py demo.sqlite3
    set CRM_DB=demo.sqlite3  (Windows)  |  export CRM_DB=demo.sqlite3  (Linux/Mac)
    python run.py

Вход: admin@demo.local / demo12345 (все демо-пароли такие же: irina@demo.local и т.д.)
Рабочую базу этот скрипт не трогает: он отказывается писать в существующий файл.
"""
import datetime as dt
import os
import random
import sqlite3
import sys

from werkzeug.security import generate_password_hash

path = sys.argv[1] if len(sys.argv) > 1 else "demo.sqlite3"
if os.path.exists(path):
    sys.exit(f"Файл {path} уже существует — укажите новое имя.")
os.environ["CRM_DB"] = path

from crm import create_app  # noqa: E402  (создаёт таблицы)

create_app()
db = sqlite3.connect(path)
db.execute("PRAGMA foreign_keys = ON")
rnd = random.Random(42)
today = dt.date.today()
PW = generate_password_hash("demo12345")


def person(first, last, stufe, coef, parent, email=None, admin=0, cabinet=True, birth=None, goal=None):
    cur = db.execute(
        """INSERT INTO persons (parent_id, first_name, last_name, stufe, coef, email, is_admin,
                                password_hash, phone, birth_date, start_date, goal_ke_month)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (parent, first, last, stufe, coef, email, admin, PW if cabinet else None,
         f"+49 15{rnd.randint(1, 7)} {rnd.randint(1000000, 9999999)}", birth,
         (today - dt.timedelta(days=rnd.randint(60, 1500))).isoformat(), goal))
    return cur.lastrowid


soon = (today + dt.timedelta(days=4)).replace(year=1988).isoformat()
viktor = person("Виктор", "Берг", "RGS", 10, None, "admin@demo.local", admin=1, birth="1982-03-14", goal=250)
irina = person("Ирина", "Ланге", "AL", 9, viktor, "irina@demo.local", birth=soon, goal=180)
dmitri = person("Дмитрий", "Шмидт", "VBA", 6, viktor, "dmitri@demo.local", birth="1991-07-02", goal=120)
oleg = person("Олег", "Майер", "VM", 2, viktor, "oleg@demo.local", birth="1996-11-30")
svetlana = person("Светлана", "Кох", "VM", 1.5, irina, "svetlana@demo.local", birth="1993-05-21")
pavel = person("Павел", "Вебер", "VM", 1, irina, "pavel@demo.local")
anna = person("Анна", "Фишер", "VM", 2, dmitri, "anna@demo.local", birth="1999-01-09")
yulia = person("Юлия", "Беккер", "VM", 1, svetlana, cabinet=False)
db.execute("UPDATE persons SET invite_hash = 'demo', invite_expires = ? WHERE id = ?",
           ((today + dt.timedelta(days=10)).isoformat() + "T12:00", yulia))

FIRST = ["Алексей", "Мария", "Сергей", "Елена", "Андрей", "Наталья", "Михаил", "Ольга", "Николай",
         "Татьяна", "Артём", "Екатерина", "Иван", "Анастасия", "Роман", "Ксения", "Lukas", "Sophie",
         "Jonas", "Lena", "Felix", "Marie", "Tobias", "Julia", "Daniel", "Laura", "Stefan", "Nina"]
LAST = ["Иванов", "Петрова", "Кузнецов", "Миллер", "Шульц", "Новикова", "Волков", "Зайцева", "Klein",
        "Wolf", "Neumann", "Schröder", "Braun", "Hoffmann", "Krüger", "Hartmann", "Lang", "Werner",
        "Попов", "Соколова", "Лебедев", "Морозова", "Richter", "Zimmermann", "Schäfer", "Bauer"]
PROF = ["Инженер", "Медсестра", "Логист", "Учитель", "IT-разработчик", "Студентка", "Электрик",
        "Бухгалтер", "Продавец", "Врач", "Pflegefachkraft", "Mechatroniker", "Erzieherin", None, None]
PRODUCTS = ["Altersvorsorge (privat)", "Berufsunfähigkeit (BU)", "Bausparvertrag", "Investment / Fonds",
            "KFZ-Versicherung", "Haftpflicht / Hausrat", "Baufinanzierung", "Risikolebensversicherung",
            "bAV (betriebliche Vorsorge)", "KV-Zusatzversicherung", "Ratenkredit / Umschuldung"]
TEMPS = ["very_hot"] * 2 + ["hot"] * 4 + ["warm"] * 6 + ["lukewarm"] * 5 + ["cold"] * 4

profiles = {  # сколько контактов, активность встреч в неделю
    viktor: (46, 6), irina: (38, 5), dmitri: (27, 4), oleg: (12, 1),
    svetlana: (24, 3), pavel: (9, 0), anna: (31, 4), yulia: (6, 0),
}

contacts = {}
for pid, (n, _) in profiles.items():
    contacts[pid] = []
    for i in range(n):
        created = today - dt.timedelta(days=rnd.randint(0, 120))
        temp = rnd.choice(TEMPS)
        kind = "client" if rnd.random() < 0.3 else "prospect"
        status = rnd.choice(["new", "new", "appointment", "in_work", "followup", "no_chance"])
        if kind == "client":
            status = rnd.choice(["in_work", "appointment"])
        nad = None
        if status in ("followup", "new") and rnd.random() < 0.45:
            nad = (today + dt.timedelta(days=rnd.randint(-6, 12))).isoformat()
        cur = db.execute(
            """INSERT INTO contacts (owner_id, first_name, last_name, phone, age, profession, channel,
                                     recommended_by, temperature, kind, status, partner_interest,
                                     next_action, next_action_date, comment, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (pid, rnd.choice(FIRST), rnd.choice(LAST), f"+49 1{rnd.randint(50, 79)} {rnd.randint(100000, 9999999)}",
             rnd.choice([None, rnd.randint(19, 64)]), rnd.choice(PROF),
             rnd.choice(["warm", "warm", "recommendation", "other"]), None, temp, kind, status,
             1 if rnd.random() < 0.12 else 0,
             rnd.choice(["Перезвонить", "Договориться о термине", "Отправить расчёт", None]) if nad else None,
             nad, None, created.isoformat() + " 10:00:00"))
        cid = cur.lastrowid
        contacts[pid].append(cid)
        for _ in range(rnd.choice([0, 0, 1, 1, 2, 3])):
            db.execute("INSERT INTO potentials (contact_id, product, ke) VALUES (?, ?, ?)",
                       (cid, rnd.choice(PRODUCTS), rnd.choice([5, 8, 10, 12, 15, 20, 25, 40, 60])))
        if kind == "client":
            for _ in range(rnd.choice([1, 1, 2])):
                d = today - dt.timedelta(days=rnd.randint(0, 80))
                db.execute("INSERT INTO deals (contact_id, date, product, ke, source) VALUES (?, ?, ?, ?, ?)",
                           (cid, d.isoformat(), rnd.choice(PRODUCTS), rnd.choice([6, 10, 14, 18, 25, 32, 45]),
                            "service" if rnd.random() < 0.25 else "consult"))

STAGE_FLOW = ["contact", "first", "first", "analysis", "consult", "consult", "closing", "service",
              "seminar", "recruiting", "advocate", "cold"]
FORMATS = ["offline", "offline", "online", "call"]
for pid, (_, per_week) in profiles.items():
    if not per_week:
        continue
    day = today - dt.timedelta(days=42)
    while day <= today + dt.timedelta(days=30):
        if day.weekday() < 6 and rnd.random() < per_week / 6:
            for _ in range(rnd.choice([1, 1, 2])):
                stage = rnd.choice(STAGE_FLOW)
                if day < today:
                    status = "done" if rnd.random() < 0.78 else ("cancelled" if rnd.random() < 0.8 else "planned")
                else:
                    status = "planned"
                fmt = "call" if stage in ("cold", "contact") else rnd.choice(FORMATS)
                exp = rnd.choice([10, 15, 20, 30, 40]) if stage in ("consult", "closing") else None
                db.execute(
                    """INSERT INTO meetings (owner_id, contact_id, date, time, duration_min, format, stage,
                                             status, expected_ke, created_by, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (pid, rnd.choice(contacts[pid]), day.isoformat(),
                     f"{rnd.choice([9, 10, 11, 13, 15, 17, 18, 19]):02d}:{rnd.choice(['00', '30'])}",
                     rnd.choice([30, 60, 90]), fmt, stage, status, exp,
                     viktor if rnd.random() < 0.3 else pid,
                     min(day - dt.timedelta(days=rnd.randint(2, 10)), today).isoformat() + " 12:00:00"))
        if day.weekday() == 1 and day >= today - dt.timedelta(days=7):   # тим-митинг по вторникам
            db.execute("""INSERT INTO meetings (owner_id, title, date, time, format, stage, status, created_by)
                          VALUES (?, 'Тим-митинг в офисе', ?, '19:00', 'offline', 'training', ?, ?)""",
                       (pid, day.isoformat(), "done" if day < today else "planned", viktor))
        if day.weekday() == 5 and rnd.random() < 0.5:
            db.execute("""INSERT INTO meetings (owner_id, title, date, time, format, stage, status, created_by)
                          VALUES (?, 'Семья', ?, '10:00', 'private', 'other', 'planned', ?)""",
                       (pid, day.isoformat(), pid))
        day += dt.timedelta(days=1)

from crm.demo import add_week_plans  # noqa: E402

for pid, (_, per_week) in profiles.items():
    if per_week:
        add_week_plans(db, pid, rnd, scale=1.0 if pid in (viktor, irina, dmitri) else 0.5, today=today)

db.commit()
print(f"Демо-база создана: {path}")
print("Вход: admin@demo.local / demo12345")
