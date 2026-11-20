"""Помощники для демо- и тестовых данных (используются seed_demo.py и seed_test_structure.py)."""
import datetime as dt

from .plan import AUTO, month_weeks

# Типичный план на неделю для бетроера (для VM масштабируется вниз)
WEEK_SOLL = {
    "fa_contacts": (12, 30), "fa_agreed": (3, 8), "fa_held": (2, 6), "fa_created": (1, 4),
    "fa_referrals": (4, 12), "fa_recruit": (0, 2), "fa_interest": (0, 2),
    "br_agreed": (2, 4), "br_held": (1, 3), "br_clients": (1, 2), "br_ke": (20, 60),
    "br_referrals": (2, 5), "br_recruit": (0, 1), "br_interest": (0, 1),
    "st_agreed": (1, 2), "st_held": (1, 2), "st_ke": (8, 20),
    "st_referrals": (1, 3), "st_recruit": (0, 1), "st_interest": (0, 1),
    "aw_contacts": (3, 8), "aw_interest": (1, 3),
}


def add_week_plans(db, person_id, rnd, scale=1.0, today=None):
    """План (одинаковый на все недели месяца) на прошлый, текущий и следующий месяц
    и ручной факт по прошедшим неделям для показателей, которые не считаются сами."""
    today = today or dt.date.today()
    first = today.replace(day=1)
    months = [(first - dt.timedelta(days=1)).replace(day=1), first,
              (first + dt.timedelta(days=32)).replace(day=1)]
    for m in months:
        soll = {}
        for key, (lo, hi) in WEEK_SOLL.items():
            v = round(rnd.uniform(lo, hi) * scale)
            if key.endswith("_ke"):
                v = round(rnd.uniform(lo, hi) * scale / 5) * 5
            soll[key] = v
        for w in month_weeks(m.year, m.month):
            ended = w + dt.timedelta(days=6) < today
            for key, s in soll.items():
                ist = None
                if ended and key not in AUTO:
                    ist = max(0, round(s * rnd.uniform(0.3, 1.4)))
                db.execute("""INSERT OR REPLACE INTO week_plan (person_id, week, metric, soll, ist)
                              VALUES (?, ?, ?, ?, ?)""", (person_id, w.isoformat(), key, s, ist))


# ---------------------------------------------------------------- рост структуры (демо)
GROWTH_MARK = "[рост]"
# Путь от входа до ступени — для демо-истории повышений
STUFE_PATH = {
    "VM": ["VM"], "VBAS": ["VM", "VBAS"], "VBAK": ["VM", "VBAK"], "AL": ["VM", "VBAK", "AL"],
    "RGS": ["VM", "VBAK", "AL", "RGS"], "GS": ["VM", "VBAK", "AL", "RGS", "GS"],
}
# Сколько единиц в месяц лично (от, до) — для демо-истории сделок
MONTH_UNITS = {"VM": (8, 30), "VBAS": (15, 40), "VBAK": (45, 95), "AL": (120, 190), "RGS": (150, 240),
               "GS": (180, 280)}
DEMO_PRODUCTS = ["Altersvorsorge (privat)", "Berufsunfähigkeit (BU)", "Bausparvertrag", "Investment / Fonds",
                 "Baufinanzierung", "Risikolebensversicherung", "bAV (betriebliche Vorsorge)"]
DEMO_FIRST = ["Алина", "Богдан", "Вера", "Глеб", "Дарина", "Егор", "Жанна", "Захар", "Инна", "Кирилл",
              "Лидия", "Марк", "Нелли", "Оскар", "Полина", "Ростислав", "Сабина", "Тимур", "Lea", "Jan",
              "Mia", "Paul", "Emma", "Ben"]
DEMO_LAST = ["Абрамов", "Белова", "Гусев", "Данилова", "Ершов", "Жукова", "Зимин", "Карпова", "Лапин",
             "Мельник", "Орлова", "Пестов", "Fischer", "Weber", "Becker", "Schulz", "Koch", "Vogel"]


def add_growth(db, ids, rnd, today=None, created_by=None, deals=True):
    """Демо-данные для роста структуры у людей ids: история ступеней, сделки за год,
    кандидаты в партнёры с этапами и годовой план. Повторный запуск всё пересоздаёт."""
    today = today or dt.date.today()
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    # 1. убираем то, что создавали раньше
    db.execute(f"DELETE FROM contacts WHERE owner_id IN ({marks}) AND comment LIKE ?", [*ids, GROWTH_MARK + "%"])
    db.execute(f"""DELETE FROM recruit_log WHERE contact_id IN (SELECT id FROM contacts WHERE owner_id IN ({marks}))""", ids)
    db.execute(f"""UPDATE contacts SET recruit_stage = NULL, recruit_info_date = NULL, joined_person_id = NULL,
                   partner_interest = 0 WHERE owner_id IN ({marks})""", ids)
    db.execute(f"DELETE FROM stufe_history WHERE person_id IN ({marks})", ids)
    db.execute(f"DELETE FROM year_goals WHERE person_id IN ({marks}) AND year = ?", [*ids, today.year])

    people = {r[0]: {"id": r[0], "parent": r[1], "stufe": r[2], "start": r[3], "first": r[4], "last": r[5],
                     "phone": r[6]}
              for r in db.execute(f"""SELECT id, parent_id, stufe, start_date, first_name, last_name, phone
                                      FROM persons WHERE id IN ({marks}) ORDER BY id""", ids)}
    counts = {"promotions": 0, "deals": 0, "candidates": 0, "goals": 0}

    # 2. история ступеней: вход как VM, затем повышения
    for p in people.values():
        path = STUFE_PATH.get(p["stufe"], [p["stufe"]])
        start = dt.date.fromisoformat(p["start"]) if p["start"] else today - dt.timedelta(days=200)
        need = (len(path) - 1) * 150 + 30
        if (today - start).days < need:
            start = today - dt.timedelta(days=need + rnd.randint(0, 120))
            p["start"] = start.isoformat()
            db.execute("UPDATE persons SET start_date = ? WHERE id = ?", (p["start"], p["id"]))
        db.execute("INSERT INTO stufe_history (person_id, stufe, date, kind, created_by) VALUES (?, ?, ?, 'start', ?)",
                   (p["id"], path[0], p["start"], created_by))
        span = (today - start).days - 20
        for i, st in enumerate(path[1:], 1):
            when = start + dt.timedelta(days=round(span * i / len(path)) + rnd.randint(-15, 15))
            db.execute("""INSERT INTO stufe_history (person_id, stufe, date, kind, created_by)
                          VALUES (?, ?, ?, 'promotion', ?)""", (p["id"], st, when.isoformat(), created_by))
            counts["promotions"] += 1

    # 3. сделки за прошедший год (последние 45 дней уже заполнены основным сидом)
    if deals:
        for p in people.values():
            lo, hi = MONTH_UNITS.get(p["stufe"], (10, 30))
            start = dt.date.fromisoformat(p["start"])
            clients = []
            for _ in range(rnd.randint(3, 6)):
                clients.append(db.execute(
                    """INSERT INTO contacts (owner_id, first_name, last_name, channel, temperature, kind, status,
                                             comment, created_at)
                       VALUES (?, ?, ?, 'recommendation', ?, 'client', 'in_work', ?, ?)""",
                    (p["id"], rnd.choice(DEMO_FIRST), rnd.choice(DEMO_LAST), rnd.choice(["hot", "warm", "warm"]),
                     f"{GROWTH_MARK} клиент из демо-истории сделок",
                     max(start, today - dt.timedelta(days=365)).isoformat() + " 09:00:00")).lastrowid)
            day = max(start, today - dt.timedelta(days=360))
            last = today - dt.timedelta(days=46)
            while day <= last:
                month_end = min((day.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1), last)
                units = rnd.uniform(lo, hi) * (0.4 if rnd.random() < 0.15 else 1)
                while units > 4:
                    ke = min(units, rnd.choice([6, 10, 14, 18, 24, 30, 40, 55]))
                    d = day + dt.timedelta(days=rnd.randint(0, max(0, (month_end - day).days)))
                    db.execute("INSERT INTO deals (contact_id, date, product, ke, source) VALUES (?, ?, ?, ?, ?)",
                               (rnd.choice(clients), d.isoformat(), rnd.choice(DEMO_PRODUCTS), round(ke),
                                "service" if rnd.random() < 0.2 else "consult"))
                    counts["deals"] += 1
                    units -= ke
                day = month_end + dt.timedelta(days=1)

    # 4. кандидаты: кто уже стал партнёром, и кто сейчас в воронке
    def log(cid, stages):
        for st, d in stages:
            db.execute("INSERT INTO recruit_log (contact_id, stage, date, created_by) VALUES (?, ?, ?, ?)",
                       (cid, st, d.isoformat(), created_by))

    kids = {}
    for p in people.values():
        if p["parent"] in people:
            kids.setdefault(p["parent"], []).append(p)
    for p in people.values():
        for k in kids.get(p["id"], []):
            joined = dt.date.fromisoformat(k["start"])
            cid = db.execute(
                """INSERT INTO contacts (owner_id, first_name, last_name, phone, channel, temperature, kind, status,
                                         partner_interest, recruit_stage, recruit_info_date, joined_person_id,
                                         comment, created_at)
                   VALUES (?, ?, ?, ?, 'warm', 'hot', 'prospect', 'in_work', 1, 'joined', ?, ?, ?, ?)""",
                (p["id"], k["first"], k["last"], k["phone"], (joined - dt.timedelta(days=21)).isoformat(), k["id"],
                 f"{GROWTH_MARK} кандидат, ставший партнёром",
                 (joined - dt.timedelta(days=45)).isoformat() + " 09:00:00")).lastrowid
            log(cid, [("interest", joined - dt.timedelta(days=40)), ("invited", joined - dt.timedelta(days=30)),
                      ("attended", joined - dt.timedelta(days=21)), ("talk", joined - dt.timedelta(days=12)),
                      ("joined", joined)])
            counts["candidates"] += 1
        n = rnd.randint(0, 2) if p["stufe"] in ("VM", "VBAS") else rnd.randint(3, 7)
        prospects = [r[0] for r in db.execute(
            """SELECT id FROM contacts WHERE owner_id = ? AND kind = 'prospect' AND recruit_stage IS NULL
               AND (comment IS NULL OR comment NOT LIKE ?)""", (p["id"], GROWTH_MARK + "%"))]
        rnd.shuffle(prospects)
        order = ["interest", "invited", "attended", "talk"]
        for cid in prospects[:n]:
            stage = rnd.choice(["interest", "interest", "invited", "attended", "talk", "declined"])
            first = today - dt.timedelta(days=rnd.randint(5, 150))
            steps, d = [], first
            target = order.index(stage) if stage in order else rnd.randint(1, 3)
            for st in order[:target + 1]:
                steps.append((st, d))
                d = min(today, d + dt.timedelta(days=rnd.randint(4, 14)))
            if stage == "declined":
                steps.append(("declined", d))
            info = next((x[1] for x in steps if x[0] == "attended"), None) or \
                (today + dt.timedelta(days=rnd.randint(2, 12)) if stage == "invited" else None)
            db.execute("""UPDATE contacts SET partner_interest = 1, recruit_stage = ?, recruit_info_date = ?
                          WHERE id = ?""", (stage, info.isoformat() if info else None, cid))
            log(cid, steps)
            counts["candidates"] += 1

    # 5. годовой план на текущий год
    def goal(pid, metric, months, value):
        for m in months:
            db.execute("""INSERT OR REPLACE INTO year_goals (person_id, year, month, metric, ziel, updated_by)
                          VALUES (?, ?, ?, ?, ?, ?)""", (pid, today.year, m, metric, value, created_by))
            counts["goals"] += 1

    def branch(pid):
        out = []
        for k in kids.get(pid, []):
            out.append(k)
            out.extend(branch(k["id"]))
        return out

    allm = range(1, 13)
    for p in people.values():
        lo, hi = MONTH_UNITS.get(p["stufe"], (10, 30))
        goal(p["id"], "eigen", allm, round((lo + hi) / 2 * 1.15 / 5) * 5)
        below = branch(p["id"])
        if below:
            grp = sum((MONTH_UNITS.get(k["stufe"], (10, 30))[0] + MONTH_UNITS.get(k["stufe"], (10, 30))[1]) / 2
                      for k in below)
            goal(p["id"], "gruppe", allm, round(grp * 1.2 / 10) * 10)
        if p["stufe"] in ("VM", "VBAS"):
            goal(p["id"], "cand_direct", (3, 6, 9, 12), 1)
            continue
        goal(p["id"], "cand_direct", allm, 3 if p["stufe"] == "VBAK" else 4)
        goal(p["id"], "vm_direct", (2, 4, 6, 8, 10, 12) if p["stufe"] == "VBAK" else allm, 1)
        if p["stufe"] != "VBAK":
            goal(p["id"], "vba_direct", (3, 6, 9, 12), 1)
            goal(p["id"], "al_direct", (12,), 1)
        if any(kids.get(k["id"]) for k in kids.get(p["id"], [])):
            goal(p["id"], "cand_indirect", allm, 3)
            goal(p["id"], "vm_indirect", (3, 6, 9, 12), 1)
    return counts
