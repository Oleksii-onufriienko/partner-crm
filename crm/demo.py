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


# ---------------------------------------------------------------- наставничество и ежедневная работа (демо)
ORGA_WELL = ["Провёл все запланированные первые термины", "Договорился о 4 терминах за один вечер",
             "Получил 6 рекомендаций после бератунга", "Взял на Info двух кандидатов", "Закрыл первую сделку по BU"]
ORGA_WHY = ["Звонил по плану каждый вечер", "Готовился к разговору по AK1", "Сразу просил рекомендации",
            "Работал по Musterwoche"]
ORGA_IMPROVE = ["Больше звонков в начале недели", "Отмечать итоги встреч сразу", "Просить рекомендации на каждом термине",
                "Чаще звать на Karriere-Info"]
ORGA_MEASURES = ["Пн и Ср 18–20 — обзвон по Marktpotenzial", "После каждой встречи — итог в CRM в тот же день",
                 "Записать 10 новых людей в Marktpotenzial", "Пригласить 2 человек на Info в четверг"]
REFL_GOALS = ["10 разговоров в день по Marktpotenzial", "3 финанализа в неделю", "2 человека на Karriere-Info",
              "Сдать экзамен VM", "Первая сделка до конца месяца", "Довести Marktpotenzial до 50 человек"]
MUSTER = [  # (дни, с, до, вид, подпись)
    ((0, 1, 2, 3, 4), "08:00", "16:30", "job", "Основная работа"),
    ((0, 2), "18:00", "20:30", "vb", "Звонки и термины"),
    ((1,), "19:00", "21:00", "team", "Тим-митинг"),
    ((3,), "18:30", "21:00", "vb", "Финанализы"),
    ((5,), "10:00", "13:00", "vb", "Бератунги"),
    ((4,), "18:00", "19:30", "hobby", "Спорт"),
    ((6,), "11:00", "18:00", "family", "Семья"),
]


def add_coaching(db, ids, rnd, today=None, created_by=None):
    """Демо для пунктов Б и В: ORGA за 6 недель, Reflexionsgespräche, старт новичков, звонки, цели, Musterwoche.
    Повторный запуск всё пересоздаёт."""
    import json as _json
    today = today or dt.date.today()
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    for table, col in (("orga_checks", "person_id"), ("reflections", "person_id"), ("onboarding", "person_id"),
                       ("calls", "owner_id"), ("future_goals", "person_id"), ("muster_blocks", "person_id")):
        db.execute(f"DELETE FROM {table} WHERE {col} IN ({marks})", ids)
    people = {r[0]: {"id": r[0], "parent": r[1], "stufe": r[2], "start": r[3], "coef": r[4]} for r in db.execute(
        f"SELECT id, parent_id, stufe, start_date, coef FROM persons WHERE id IN ({marks})", ids)}
    keys = ["service", "lead", "planning", "contact", "evidence", "analysis", "referrals", "recruit", "consult"]
    counts = {"orga": 0, "reflections": 0, "calls": 0}
    monday = today - dt.timedelta(days=today.weekday())
    for p in people.values():
        # ORGA: 6 недель, у части людей прошлой недели нет — так видно слабое место
        base = {k: rnd.randint(3, 7) for k in keys}
        skip_last = rnd.random() < 0.25
        for i in range(6, 0, -1):
            if i == 1 and skip_last:
                continue
            if rnd.random() < 0.15:
                continue
            for k in keys:
                base[k] = max(0, min(10, base[k] + rnd.choice([-1, 0, 0, 1, 1])))
            week = monday - dt.timedelta(days=7 * i)
            db.execute("""INSERT INTO orga_checks (person_id, week, insight, went_well, why_well, improve, measures,
                              measures_when, controller, prev_done, reward, reward_for, tables_ready, next_plan_ready,
                              potential_ready, skills, created_at, updated_at)
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                       (p["id"], week.isoformat(), rnd.choice(["Первых терминов меньше плана — мало звонков",
                                                               "План выполнен, кроме бератунгов",
                                                               "Финанализов больше плана"]),
                        rnd.choice(ORGA_WELL), rnd.choice(ORGA_WHY), rnd.choice(ORGA_IMPROVE), rnd.choice(ORGA_MEASURES),
                        (week + dt.timedelta(days=rnd.randint(8, 11))).isoformat(), "Наставник",
                        rnd.choice([1, 1, 0]), rnd.choice(["Кино", "Ужин в ресторане", "Свободный вечер"]),
                        "За выполненный план недели", 1, rnd.choice([0, 1]), rnd.choice([0, 1]), _json.dumps(base),
                        (week + dt.timedelta(days=7)).isoformat() + " 08:00:00",
                        (week + dt.timedelta(days=7)).isoformat() + " 08:00:00"))
            counts["orga"] += 1
        # Reflexionsgespräche с наставником: каждые 4–6 недель от входа
        start = dt.date.fromisoformat(p["start"]) if p["start"] else today - dt.timedelta(days=120)
        d = max(start, today - dt.timedelta(days=170)) + dt.timedelta(days=rnd.randint(25, 40))
        n = 0
        while d < today - dt.timedelta(days=3) and n < 4:
            nxt = d + dt.timedelta(days=rnd.randint(28, 42))
            goals = rnd.sample(REFL_GOALS, 3)
            res = {"analyses": rnd.randint(2, 9), "consults": rnd.randint(1, 6), "referrals": rnd.randint(3, 15),
                   "clients": rnd.randint(0, 4), "partners": rnd.randint(0, 1), "info": rnd.randint(0, 3),
                   "vm": rnd.randint(0, 1), "units": rnd.randint(20, 160)}
            db.execute("""INSERT INTO reflections (person_id, date, place, people, satisfaction, goals_reached, improve,
                              results, period_from, cp_clients, cp_clients_goal, cp_partners, cp_partners_goal,
                              goal1, goal2, goal3, work_plan, intent, next_date, next_time, created_by)
                          VALUES (?, ?, 'Офис', 'coach', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '18:00', ?)""",
                       (p["id"], d.isoformat(), rnd.randint(3, 5), rnd.choice(["Да, две из трёх", "Частично", "Да, все"]),
                        rnd.choice(ORGA_IMPROVE), _json.dumps(res), (d - dt.timedelta(days=35)).isoformat(),
                        rnd.randint(25, 80), rnd.choice([60, 80, 100]), rnd.randint(1, 8), rnd.choice([10, 15, 20]),
                        *goals, "Два вечера в неделю — звонки, суббота — бератунги.",
                        rnd.choice(["side", "side", "main", "vb"]), nxt.isoformat() if nxt > today else None,
                        p["parent"] if p["parent"] else created_by))
            counts["reflections"] += 1
            n += 1
            d = nxt
        # Старт: ручные шаги и темы обучения у тех, кто ещё в Nebenberuf
        if p["stufe"] in ("VM", "VBAS", "VBAK"):
            day = start
            for step in ("info", "starter", "ak1"):
                day = day + dt.timedelta(days=rnd.randint(2, 12))
                if day < today and rnd.random() < 0.85:
                    db.execute("INSERT INTO onboarding (person_id, step, date, updated_by) VALUES (?, ?, ?, ?)",
                               (p["id"], step, day.isoformat(), created_by))
            if p["stufe"] != "VM" or rnd.random() < 0.3:
                db.execute("INSERT INTO onboarding (person_id, step, date, result, updated_by) VALUES (?, 'vm_exam', ?, 'passed', ?)",
                           (p["id"], min(today, start + dt.timedelta(days=rnd.randint(40, 90))).isoformat(), created_by))
            if p["stufe"] == "VBAK" and rnd.random() < 0.7:
                db.execute("INSERT INTO onboarding (person_id, step, date, result, updated_by) VALUES (?, 'vba_exam', ?, 'passed', ?)",
                           (p["id"], min(today, start + dt.timedelta(days=rnd.randint(120, 220))).isoformat(), created_by))
            for i, topic in enumerate(rnd.sample(["Kontaktpyramide", "Fürsprechergespräch", "Finanzanalyse",
                                                  "Terminvereinbarung", "Empfehlungen", "Altersvorsorge"], rnd.randint(1, 4)), 1):
                db.execute("INSERT INTO onboarding (person_id, step, date, note, updated_by) VALUES (?, ?, ?, ?, ?)",
                           (p["id"], f"topic{i}", min(today, start + dt.timedelta(days=7 * i)).isoformat(), topic, created_by))
        # Fürsprechergespräche — проведённые встречи этапа advocate в первые недели
        hot = [r[0] for r in db.execute("SELECT id FROM contacts WHERE owner_id = ? AND temperature IN ('very_hot', 'hot') LIMIT 6",
                                        (p["id"],))]
        for i, cid in enumerate(hot[:rnd.randint(1, 4)]):
            md = start + dt.timedelta(days=5 + 4 * i)
            if md < today:
                db.execute("""INSERT INTO meetings (owner_id, contact_id, date, time, duration_min, format, stage, status,
                                                    created_by, created_at)
                              VALUES (?, ?, ?, '18:00', 60, 'offline', 'advocate', 'done', ?, ?)""",
                           (p["id"], cid, md.isoformat(), p["id"], (md - dt.timedelta(days=3)).isoformat() + " 12:00:00"))
        # Звонки за последние 10 дней
        contacts = [r[0] for r in db.execute("SELECT id FROM contacts WHERE owner_id = ? AND status != 'no_chance'", (p["id"],))]
        if contacts:
            for back in range(10, -1, -1):
                day = today - dt.timedelta(days=back)
                if day.weekday() == 6:
                    continue
                for _ in range(rnd.randint(0, 6 if p["stufe"] == "VM" else 10)):
                    res = rnd.choice(["no_answer"] * 4 + ["callback"] * 3 + ["appointment"] * 2 + ["no_chance"])
                    db.execute("""INSERT INTO calls (owner_id, contact_id, date, time, result, created_by)
                                  VALUES (?, ?, ?, ?, ?, ?)""",
                               (p["id"], rnd.choice(contacts), day.isoformat(),
                                f"{rnd.randint(17, 20):02d}:{rnd.choice(['05', '20', '35', '50'])}", res, p["id"]))
                    counts["calls"] += 1
        # Цели и Musterwoche
        income = rnd.choice([1000, 1500, 2000, 3000]) if p["stufe"] in ("VM", "VBAS", "VBAK") else rnd.choice([5000, 7000, 9000])
        goals = {"fin_month_this": income, "fin_year_this": income * 12, "fin_month_next": round(income * 1.6),
                 "fin_year_next": round(income * 1.6) * 12, "fin_month_five": income * 4, "fin_year_five": income * 48,
                 "mat_this": rnd.choice(["Новый ноутбук", "Отпуск у моря"]), "mat_next": "Машина", "mat_five": "Своя квартира",
                 "pers_this": "Спорт два раза в неделю", "pers_next": "Больше времени с семьёй", "pers_five": "Финансовая свобода",
                 "rewards": [{"what": "Ужин в ресторане", "when": (today + dt.timedelta(days=20)).isoformat(),
                              "why": "План месяца"}],
                 "motto": rnd.choice(["Мой результат — моя цель", "На меня можно положиться"])}
        db.execute("INSERT INTO future_goals (person_id, data, updated_by) VALUES (?, ?, ?)",
                   (p["id"], _json.dumps(goals, ensure_ascii=False), created_by))
        for days, s, e, kind, title in MUSTER:
            if kind == "job" and p["stufe"] not in ("VM", "VBAS", "VBAK"):
                continue
            for wd in days:
                db.execute("""INSERT INTO muster_blocks (person_id, weekday, start, end, kind, title)
                              VALUES (?, ?, ?, ?, ?, ?)""", (p["id"], wd, s, e, kind, title))
    return counts
