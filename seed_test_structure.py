"""Тестовая структура под администратором — для демонстрации и тестов.

    python seed_test_structure.py add    ПУТЬ/К/crm.sqlite3
    python seed_test_structure.py remove ПУТЬ/К/crm.sqlite3
    python seed_test_structure.py plan   ПУТЬ/К/crm.sqlite3
    python seed_test_structure.py growth ПУТЬ/К/crm.sqlite3

add    — добавляет под первого администратора: 3 VBAK, 1 AL (у него ещё 1 VBAK) и 10 VM,
         у каждого — до 10 контактов, потенциальные сделки, встречи и немного сделок.
         и план/факт по неделям на прошлый, текущий и следующий месяц.
remove — удаляет всех тестовых людей (помечены «[ТЕСТ]» в заметке) со всеми их данными.
plan   — заново заполняет план/факт по неделям у уже добавленных тестовых людей.
growth — заново заполняет рост структуры у тестовых людей: история ступеней, сделки за год,
         кандидаты в партнёры по этапам и годовой план (Jahresplanung) на текущий год.
Телефоны вымышленные (+49 000 …). Кабинетов (паролей) у тестовых людей нет.
"""
import datetime as dt
import os
import random
import sqlite3
import sys

MARK = "[ТЕСТ]"

if len(sys.argv) != 3 or sys.argv[1] not in ("add", "remove", "plan", "growth"):
    sys.exit(__doc__)
cmd, path = sys.argv[1], os.path.abspath(os.path.expanduser(sys.argv[2]))
if not os.path.exists(path):
    sys.exit(f"Базы {path} нет.")

# Приводим схему базы к текущей версии (новые таблицы и колонки)
os.environ["CRM_DB"] = path
os.environ.setdefault("CRM_INSTANCE", os.path.dirname(path))
from crm import create_app  # noqa: E402
from crm.demo import add_growth, add_week_plans  # noqa: E402

create_app()
db = sqlite3.connect(path)
db.execute("PRAGMA foreign_keys = ON")


def test_ids():
    return [r[0] for r in db.execute("SELECT id FROM persons WHERE note LIKE ?", (MARK + "%",))]


if cmd == "remove":
    ids = test_ids()
    if not ids:
        sys.exit("Тестовых людей нет.")
    marks = ",".join("?" * len(ids))
    db.execute(f"DELETE FROM meetings WHERE owner_id IN ({marks})", ids)
    db.execute(f"DELETE FROM contacts WHERE owner_id IN ({marks})", ids)   # сделки и потенциал — каскадом
    # сначала самые нижние уровни
    while True:
        left = test_ids()
        if not left:
            break
        leaves = [i for i in left if not db.execute("SELECT 1 FROM persons WHERE parent_id = ?", (i,)).fetchone()]
        if not leaves:
            sys.exit("Под тестовыми людьми есть настоящие — удаление остановлено.")
        db.executemany("DELETE FROM persons WHERE id = ?", [(i,) for i in leaves])
    db.commit()
    print(f"Удалено тестовых людей: {len(ids)}")
    sys.exit()

if cmd == "plan":
    ids = test_ids()
    if not ids:
        sys.exit("Тестовых людей нет. Сначала: python seed_test_structure.py add " + path)
    rnd = random.Random(7)
    marks = ",".join("?" * len(ids))
    db.execute(f"DELETE FROM week_plan WHERE person_id IN ({marks})", ids)
    n = 0
    for pid, stufe in db.execute(f"SELECT id, stufe FROM persons WHERE id IN ({marks}) ORDER BY id", ids).fetchall():
        if stufe == "VM" and rnd.random() < 0.2:
            continue                       # у пары VM плана нет — так видно сигнал
        add_week_plans(db, pid, rnd, scale=0.5 if stufe == "VM" else 1.0)
        n += 1
    db.commit()
    print(f"План/факт по неделям заполнен у {n} тестовых людей.")
    sys.exit()

if cmd == "growth":
    ids = test_ids()
    if not ids:
        sys.exit("Тестовых людей нет. Сначала: python seed_test_structure.py add " + path)
    admin_id = db.execute("SELECT id FROM persons WHERE is_admin = 1 ORDER BY id LIMIT 1").fetchone()[0]
    c = add_growth(db, ids, random.Random(11), created_by=admin_id)
    db.commit()
    print(f"Рост структуры у {len(ids)} тестовых людей: {c['promotions']} повышений, {c['deals']} сделок за год, "
          f"{c['candidates']} кандидатов, {c['goals']} целей годового плана.")
    sys.exit()

if test_ids():
    sys.exit("Тестовая структура уже есть. Сначала: python seed_test_structure.py remove " + path)
admin = db.execute("SELECT id, first_name, last_name FROM persons WHERE is_admin = 1 ORDER BY id LIMIT 1").fetchone()
if not admin:
    sys.exit("Сначала создайте кабинет администратора на сайте.")

rnd = random.Random(2026)
today = dt.date.today()


def phone():
    return f"+49 000 {rnd.randint(1000000, 9999999)}"


def person(first, last, stufe, coef, parent, goal=None):
    birth = dt.date(rnd.randint(1975, 2001), rnd.randint(1, 12), rnd.randint(1, 28)).isoformat()
    start = (today - dt.timedelta(days=rnd.randint(40, 900))).isoformat()
    cur = db.execute(
        """INSERT INTO persons (parent_id, first_name, last_name, stufe, coef, phone, birth_date,
                                start_date, goal_ke_month, note, created_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (parent, first, last, stufe, coef, phone(), birth, start, goal,
         f"{MARK} Тестовые данные для демонстрации", admin[0]))
    return cur.lastrowid


# ---- структура
vba1 = person("Марина", "Кляйн", "VBAK", 6, admin[0], 120)
vba2 = person("Андрей", "Шульц", "VBAK", 6, admin[0], 100)
vba3 = person("Наталья", "Вагнер", "VBAK", 6, admin[0], 100)
al = person("Сергей", "Хартманн", "AL", 9, admin[0], 180)
vba4 = person("Ольга", "Беккер", "VBAK", 6, al, 100)

vm_plan = [
    (vba1, "Денис", "Фогель"), (vba1, "Ирина", "Шнайдер"), (vba1, "Максим", "Лоренц"),
    (vba2, "Татьяна", "Кох"), (vba2, "Виталий", "Нойманн"),
    (vba3, "Елена", "Зайдель"), (vba3, "Артур", "Краузе"),
    (al, "Юлия", "Майер"),
    (vba4, "Роман", "Фукс"), (vba4, "Кристина", "Шмитт"),
]
vms = [person(f, l, "VM", rnd.choice([1, 1.5, 2, 2.5]), parent, rnd.choice([None, 30, 40, 50]))
       for parent, f, l in vm_plan]

# ---- контакты, встречи, сделки
FIRST = ["Алексей", "Мария", "Сергей", "Анна", "Дмитрий", "Ольга", "Михаил", "Светлана", "Николай",
         "Татьяна", "Артём", "Екатерина", "Иван", "Анастасия", "Павел", "Ксения", "Lukas", "Sophie",
         "Jonas", "Lena", "Felix", "Marie", "Tobias", "Julia", "Daniel", "Laura", "Stefan", "Nina"]
LAST = ["Иванов", "Петрова", "Кузнецов", "Миллер", "Шульц", "Новикова", "Волков", "Зайцева", "Klein",
        "Wolf", "Neumann", "Schröder", "Braun", "Hoffmann", "Krüger", "Hartmann", "Lang", "Werner",
        "Попов", "Соколова", "Лебедев", "Морозова", "Richter", "Zimmermann", "Schäfer", "Bauer"]
PROF = ["Инженер", "Медсестра", "Логист", "Учитель", "IT-разработчик", "Студентка", "Электрик",
        "Бухгалтер", "Продавец", "Врач", "Pflegefachkraft", "Mechatroniker", "Erzieherin", None]
PRODUCTS = ["Altersvorsorge (privat)", "Berufsunfähigkeit (BU)", "Bausparvertrag", "Investment / Fonds",
            "KFZ-Versicherung", "Haftpflicht / Hausrat", "Baufinanzierung", "Risikolebensversicherung",
            "bAV (betriebliche Vorsorge)", "KV-Zusatzversicherung", "Ratenkredit / Umschuldung"]
TEMPS = ["very_hot"] + ["hot"] * 3 + ["warm"] * 4 + ["lukewarm"] * 3 + ["cold"] * 2
STAGES = ["contact", "first", "first", "analysis", "consult", "consult", "closing", "service", "seminar"]

counts = {"contacts": 0, "meetings": 0, "deals": 0}
for pid in [vba1, vba2, vba3, al, vba4] + vms:
    is_vm = pid in vms
    activity = rnd.choice([0, 1, 2, 3]) if is_vm else rnd.choice([2, 3, 4])   # встреч в неделю
    contact_ids = []
    for _ in range(rnd.randint(6, 10)):
        kind = "client" if rnd.random() < 0.25 else "prospect"
        status = rnd.choice(["new", "new", "appointment", "in_work", "followup", "no_chance"])
        if kind == "client":
            status = "in_work"
        nad = (today + dt.timedelta(days=rnd.randint(-5, 10))).isoformat() \
            if status in ("new", "followup") and rnd.random() < 0.4 else None
        cid = db.execute(
            """INSERT INTO contacts (owner_id, first_name, last_name, phone, age, profession, channel,
                                     temperature, kind, status, partner_interest, next_action,
                                     next_action_date, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (pid, rnd.choice(FIRST), rnd.choice(LAST), phone(), rnd.choice([None, rnd.randint(20, 62)]),
             rnd.choice(PROF), rnd.choice(["warm", "warm", "recommendation", "other"]), rnd.choice(TEMPS),
             kind, status, 1 if rnd.random() < 0.1 else 0,
             rnd.choice(["Перезвонить", "Договориться о термине"]) if nad else None, nad,
             (today - dt.timedelta(days=rnd.randint(0, 60))).isoformat() + " 10:00:00")).lastrowid
        contact_ids.append(cid)
        counts["contacts"] += 1
        for _ in range(rnd.choice([0, 1, 1, 2])):
            db.execute("INSERT INTO potentials (contact_id, product, ke) VALUES (?, ?, ?)",
                       (cid, rnd.choice(PRODUCTS), rnd.choice([5, 8, 10, 15, 20, 30, 40])))
        if kind == "client":
            db.execute("INSERT INTO deals (contact_id, date, product, ke, source) VALUES (?, ?, ?, ?, ?)",
                       (cid, (today - dt.timedelta(days=rnd.randint(0, 45))).isoformat(),
                        rnd.choice(PRODUCTS), rnd.choice([6, 10, 14, 18, 25, 32]),
                        "service" if rnd.random() < 0.25 else "consult"))
            counts["deals"] += 1
    if not activity:
        continue
    day = today - dt.timedelta(days=28)
    while day <= today + dt.timedelta(days=21):
        if day.weekday() < 6 and rnd.random() < activity / 6:
            stage = rnd.choice(STAGES)
            status = ("done" if rnd.random() < 0.8 else "cancelled") if day < today else "planned"
            db.execute(
                """INSERT INTO meetings (owner_id, contact_id, date, time, duration_min, format, stage,
                                         status, expected_ke, created_by, created_at)
                   VALUES (?, ?, ?, ?, 60, ?, ?, ?, ?, ?, ?)""",
                (pid, rnd.choice(contact_ids), day.isoformat(),
                 f"{rnd.choice([10, 11, 14, 16, 17, 18, 19]):02d}:{rnd.choice(['00', '30'])}",
                 "call" if stage == "contact" else rnd.choice(["offline", "offline", "online", "call"]),
                 stage, status, rnd.choice([10, 15, 20, 30]) if stage in ("consult", "closing") else None,
                 admin[0] if rnd.random() < 0.3 else pid,
                 min(day - dt.timedelta(days=rnd.randint(2, 10)), today).isoformat() + " 12:00:00"))
            counts["meetings"] += 1
        day += dt.timedelta(days=1)

for pid in [vba1, vba2, vba3, al, vba4] + vms:
    if pid in vms and rnd.random() < 0.2:
        continue
    add_week_plans(db, pid, rnd, scale=0.5 if pid in vms else 1.0, today=today)

add_growth(db, [vba1, vba2, vba3, al, vba4] + vms, rnd, today=today, created_by=admin[0])

db.commit()
print(f"Добавлено под «{admin[1]} {admin[2]}»: 15 человек (3 VBAK, 1 AL с 1 VBAK, 10 VM), "
      f"{counts['contacts']} контактов, {counts['meetings']} встреч, {counts['deals']} сделок.")
