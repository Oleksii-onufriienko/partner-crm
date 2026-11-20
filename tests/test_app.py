"""Проверки основных сценариев и прав доступа.  python -m unittest -v"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.db = os.path.join(cls.tmp, "demo.sqlite3")
        env = dict(os.environ, CRM_INSTANCE=os.path.join(cls.tmp, "inst"))
        subprocess.run([sys.executable, os.path.join(ROOT, "seed_demo.py"), cls.db], check=True,
                       env=env, cwd=ROOT, capture_output=True)
        os.environ["CRM_DB"] = cls.db
        os.environ["CRM_INSTANCE"] = os.path.join(cls.tmp, "inst")
        from crm import create_app
        cls.app = create_app({"TESTING": True})

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def client_for(self, email):
        c = self.app.test_client()
        c.get("/login")
        r = c.post("/login", data={"email": email, "password": "demo12345", "csrf_token": self.csrf(c)})
        self.assertEqual(r.status_code, 302, f"login failed for {email}")
        return c

    def csrf(self, c):
        with c.session_transaction() as s:
            return s.get("csrf") or ""

    def pid(self, last_name):
        import sqlite3
        db = sqlite3.connect(self.db)
        return db.execute("SELECT id FROM persons WHERE last_name = ?", (last_name,)).fetchone()[0]

    def first_contact(self, pid):
        import sqlite3
        db = sqlite3.connect(self.db)
        return db.execute("SELECT id FROM contacts WHERE owner_id = ? ORDER BY id LIMIT 1", (pid,)).fetchone()[0]


class PagesTest(Base):
    def test_all_pages_render_for_admin(self):
        c = self.client_for("admin@demo.local")
        for url in ["/", "/team", "/team?all=1", "/contacts", "/contacts?sort=temp", "/contacts?q=a&temperature=hot",
                    "/contacts/new", "/planner", "/meetings/new", "/stats", "/stats?scope=team",
                    "/stats?period=custom&from=2026-01-01&to=2026-12-31", "/stats?period=next6w",
                    "/account", "/people/new", f"/people/{self.pid('Ланге')}", f"/people/{self.pid('Ланге')}/edit",
                    f"/contacts/{self.first_contact(self.pid('Ланге'))}", f"/planner?person={self.pid('Ланге')}",
                    f"/stats?person={self.pid('Ланге')}&scope=team", "/plan", "/plan?scope=team",
                    "/plan/edit", "/plan?month=2026-01", f"/plan?person={self.pid('Ланге')}&scope=team",
                    f"/plan/edit?person={self.pid('Кох')}&month=2030-02"]:
            r = c.get(url)
            self.assertEqual(r.status_code, 200, url)
            self.assertNotIn(b"Traceback", r.data)

    def test_pages_render_for_vm_without_team(self):
        c = self.client_for("oleg@demo.local")
        for url in ["/", "/team", "/contacts", "/planner", "/stats", "/account", "/meetings/new", "/contacts/new",
                    "/plan", "/plan/edit", "/plan?scope=team"]:
            self.assertEqual(c.get(url).status_code, 200, url)

    def test_unauthenticated_redirects_to_login(self):
        c = self.app.test_client()
        r = c.get("/contacts")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])


class AccessTest(Base):
    def test_partner_sees_only_own_branch(self):
        c = self.client_for("irina@demo.local")
        # своя ветка — видно
        for name in ("Кох", "Вебер", "Беккер"):
            self.assertEqual(c.get(f"/people/{self.pid(name)}").status_code, 200, name)
        # соседняя ветка и наставник — не видно
        for name in ("Шмидт", "Фишер", "Берг", "Майер"):
            self.assertEqual(c.get(f"/people/{self.pid(name)}").status_code, 404, name)
            self.assertEqual(c.get(f"/contacts?person={self.pid(name)}").status_code, 404, name)
            self.assertEqual(c.get(f"/planner?person={self.pid(name)}").status_code, 404, name)
            self.assertEqual(c.get(f"/stats?person={self.pid(name)}").status_code, 404, name)
            self.assertEqual(c.get(f"/plan?person={self.pid(name)}").status_code, 404, name)
            self.assertEqual(c.get(f"/plan/edit?person={self.pid(name)}").status_code, 404, name)
            cid = self.first_contact(self.pid(name))
            self.assertEqual(c.get(f"/contacts/{cid}").status_code, 404, name)

    def test_cannot_create_contact_for_foreign_person(self):
        c = self.client_for("oleg@demo.local")
        r = c.post("/contacts/new", data={"csrf_token": self.csrf(c), "owner_id": self.pid("Ланге"),
                                          "first_name": "Хакер"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("Выберите, чей это контакт".encode(), r.data)

    def test_vm_cannot_edit_own_stufe(self):
        c = self.client_for("oleg@demo.local")
        r = c.get(f"/people/{self.pid('Майер')}/edit")
        self.assertEqual(r.status_code, 302)       # отправляет в «Мой профиль»

    def test_post_without_csrf_rejected(self):
        c = self.client_for("oleg@demo.local")
        r = c.post("/contacts", data={"first_name": "X"})
        self.assertEqual(r.status_code, 400)

    def test_cannot_move_person_under_own_partner(self):
        c = self.client_for("admin@demo.local")
        irina = self.pid("Ланге")
        r = c.post(f"/people/{irina}/edit", data={"csrf_token": self.csrf(c), "first_name": "Ирина",
                                                  "last_name": "Ланге", "stufe": "AL", "coef": "9",
                                                  "parent_id": self.pid("Кох")})
        self.assertIn("Нельзя поставить".encode(), r.data)


class FlowTest(Base):
    def test_invite_registration_flow(self):
        admin = self.client_for("admin@demo.local")
        r = admin.post("/people/new", data={"csrf_token": self.csrf(admin), "first_name": "Новый",
                                            "last_name": "Партнёр", "stufe": "VM", "coef": "",
                                            "parent_id": self.pid("Берг"), "invite": "1"})
        self.assertEqual(r.status_code, 302)
        page = admin.get(r.headers["Location"]).data.decode()
        link = re.search(r'value="(http[^"]+/invite/[^"]+)"', page).group(1)
        token_path = link.split("localhost", 1)[1]

        newbie = self.app.test_client()
        self.assertEqual(newbie.get(token_path).status_code, 200)
        r = newbie.post(token_path, data={"csrf_token": self.csrf(newbie), "email": "new@demo.local",
                                          "password": "secret123", "password2": "secret123"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(newbie.get("/").status_code, 200)
        # ссылка одноразовая
        self.assertEqual(self.app.test_client().get(token_path).status_code, 404)
        # коэффициент подставился по ступени VM
        import sqlite3
        coef = sqlite3.connect(self.db).execute("SELECT coef FROM persons WHERE email='new@demo.local'").fetchone()[0]
        self.assertEqual(coef, 1.0)

    def test_contact_deal_makes_client_and_meeting_sets_status(self):
        c = self.client_for("oleg@demo.local")
        me = self.pid("Майер")
        r = c.post("/contacts", data={"csrf_token": self.csrf(c), "person": me, "first_name": "Тест",
                                      "last_name": "Клиент", "temperature": "hot"})
        self.assertEqual(r.status_code, 302)
        import sqlite3
        db = sqlite3.connect(self.db)
        cid = db.execute("SELECT id FROM contacts WHERE first_name='Тест' AND owner_id=?", (me,)).fetchone()[0]
        c.post(f"/contacts/{cid}/potentials", data={"csrf_token": self.csrf(c), "product": "Bausparvertrag", "ke": "12,5"})
        pot = db.execute("SELECT id, ke FROM potentials WHERE contact_id=?", (cid,)).fetchone()
        self.assertEqual(pot[1], 12.5)
        r = c.post("/meetings/new", data={"csrf_token": self.csrf(c), "owner_id": me, "contact_id": cid,
                                          "date": "2030-01-07", "time": "18:00", "format": "online",
                                          "stage": "first", "status": "planned"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(db.execute("SELECT status FROM contacts WHERE id=?", (cid,)).fetchone()[0], "appointment")
        c.post(f"/contacts/{cid}/deals", data={"csrf_token": self.csrf(c), "date": "2030-01-08",
                                               "product": "Bausparvertrag", "ke": "12,5", "from_potential": pot[0]})
        self.assertEqual(db.execute("SELECT kind FROM contacts WHERE id=?", (cid,)).fetchone()[0], "client")
        self.assertEqual(db.execute("SELECT COUNT(*) FROM potentials WHERE contact_id=?", (cid,)).fetchone()[0], 0)
        r = c.get("/stats?period=custom&from=2030-01-01&to=2030-01-31")
        self.assertIn("25 €".encode(), r.data)   # 12,5 KE × 2 €

    def test_upline_plans_meeting_for_partner(self):
        c = self.client_for("irina@demo.local")
        sv = self.pid("Кох")
        r = c.post("/meetings/new", data={"csrf_token": self.csrf(c), "owner_id": sv, "title": "Совместный термин",
                                          "date": "2030-02-04", "format": "offline", "stage": "consult",
                                          "status": "planned", "expected_ke": "30"})
        self.assertEqual(r.status_code, 302)
        page = c.get(f"/planner?person={sv}&start=2030-02-04").data.decode()
        self.assertIn("Совместный термин", page)

    def test_signals_computed(self):
        c = self.client_for("admin@demo.local")
        page = c.get("/stats?scope=team").data.decode()
        self.assertIn("Слабые места", page)
        self.assertIn("Пустой план", page)   # у Павла и Олега нет встреч
        self.assertIn("меньше минимума (20)", page)
        self.assertIn("Виктор Берг ›", page)   # иерархия над именем в «Слабых местах»



class PlanTest(Base):
    def test_auto_and_manual_facts(self):
        import sqlite3
        c = self.client_for("oleg@demo.local")
        me = self.pid("Майер")
        db = sqlite3.connect(self.db)
        c.post("/contacts", data={"csrf_token": self.csrf(c), "person": me, "first_name": "План", "last_name": "Тест"})
        cid = db.execute("SELECT id FROM contacts WHERE first_name='План' AND owner_id=?", (me,)).fetchone()[0]
        c.post("/meetings/new", data={"csrf_token": self.csrf(c), "owner_id": me, "contact_id": cid,
                                      "date": "2030-01-08", "format": "offline", "stage": "first", "status": "done"})
        c.post(f"/contacts/{cid}/deals", data={"csrf_token": self.csrf(c), "date": "2030-01-09",
                                               "product": "BU", "ke": "10", "source": "service"})
        r = c.post("/plan/edit?month=2030-01", data={"csrf_token": self.csrf(c),
                                                     "s_fa_held_2030-01-07": "3", "i_fa_referrals_2030-01-07": "5",
                                                     "i_fa_held_2030-01-14": "2"})
        self.assertEqual(r.status_code, 302)
        with self.app.app_context():
            from crm import plan as P
            weeks = P.month_weeks(2030, 1)
            self.assertEqual([w.day for w in weeks], [7, 14, 21, 28])
            g = P.grids([me], weeks)[me]
            w1, w2 = g["2030-01-07"], g["2030-01-14"]
            self.assertEqual((w1["fa_held"]["soll"], w1["fa_held"]["ist"]), (3, 1))   # авто из встречи
            self.assertEqual(w1["fa_referrals"]["ist"], 5)                              # вручную
            self.assertEqual(w1["st_ke"]["ist"], 10)                                    # сделка из сервиса
            self.assertEqual(w1["br_clients"]["ist"], 1)                                # первая сделка
            self.assertTrue(w2["fa_held"]["manual"])
            self.assertEqual(w2["fa_held"]["ist"], 2)                                   # поправка вручную
        page = c.get("/plan?month=2030-01").data.decode()
        self.assertIn("Проведено первых терминов", page)

    def test_copy_previous_month(self):
        c = self.client_for("anna@demo.local")
        me = self.pid("Фишер")
        c.post("/plan/edit?month=2029-12", data={"csrf_token": self.csrf(c), "s_br_ke_2029-12-31": "40"})
        c.post("/plan/copy?month=2030-01", data={"csrf_token": self.csrf(c)})
        with self.app.app_context():
            from crm import plan as P
            weeks = P.month_weeks(2030, 1)
            g = P.grids([me], weeks)[me]
            self.assertEqual([g[w.isoformat()]["br_ke"]["soll"] for w in weeks], [40, 40, 40, 40])

    def test_team_scope_sums_branch(self):
        c = self.client_for("irina@demo.local")
        for name, val in (("Кох", "4"), ("Вебер", "6")):
            c.post(f"/plan/edit?person={self.pid(name)}&month=2030-03",
                   data={"csrf_token": self.csrf(c), "s_br_held_2030-03-04": val})
        with self.app.app_context():
            from crm import plan as P
            weeks = P.month_weeks(2030, 3)
            ids = [self.pid("Кох"), self.pid("Вебер")]
            total = P.month_totals(P.combine(P.grids(ids, weeks).values(), weeks), weeks)
            self.assertEqual(total["br_held"]["soll"], 10)


class ViewContextTest(Base):
    def test_selected_partner_sticks_across_menu(self):
        c = self.client_for("irina@demo.local")
        koch, me = self.pid("Кох"), self.pid("Ланге")
        c.get(f"/view?person={koch}&next=/contacts")
        for url in ("/contacts", "/planner", "/plan", "/stats", "/"):
            page = c.get(url).data.decode()
            self.assertIn(f'<option value="{koch}" selected', page, url)       # вверху выбран Кох
        page = c.get("/contacts").data.decode()
        import sqlite3
        name = sqlite3.connect(self.db).execute(
            "SELECT first_name FROM contacts WHERE owner_id=? ORDER BY last_name LIMIT 1", (koch,)).fetchone()[0]
        self.assertIn(name, page)
        r = c.get(f"/view?person={me}&next=/planner")
        self.assertEqual(r.headers["Location"], "/planner")
        self.assertIn(f'<option value="{me}" selected', c.get("/planner").data.decode())

    def test_cannot_view_foreign_partner(self):
        c = self.client_for("irina@demo.local")
        self.assertEqual(c.get(f"/view?person={self.pid('Шмидт')}").status_code, 404)

    def test_open_redirect_blocked(self):
        c = self.client_for("irina@demo.local")
        r = c.get(f"/view?person={self.pid('Ланге')}&next=//evil.example")
        self.assertEqual(r.headers["Location"], "/")


class ContactsListTest(Base):
    def test_sorting_and_filters(self):
        c = self.client_for("admin@demo.local")
        for key in ("name", "phone", "temp", "channel", "status", "potential", "deals", "next", "age", "new"):
            for d in ("asc", "desc"):
                self.assertEqual(c.get(f"/contacts?sort={key}&dir={d}").status_code, 200)
        for q in ("reminder=overdue", "reminder=week", "reminder=none", "potential=yes", "deals=no",
                  "age_from=30&age_to=40", "channel=recommendation&kind=client", "sort=bad&dir=bad"):
            self.assertEqual(c.get(f"/contacts?{q}").status_code, 200, q)
        page = c.get("/contacts?age_from=200").data.decode()
        self.assertIn("Под фильтр никто не подходит", page)

    def test_potential_sort_desc(self):
        import re
        c = self.client_for("admin@demo.local")
        page = c.get("/contacts?sort=potential&dir=desc").data.decode()
        cells = re.findall(r'<td class="num">([\d\s\u202f,]+|—)</td>', page)
        nums = [float(x.replace("\u202f", "").replace(",", ".")) for x in cells[::2] if x != "—"]
        self.assertEqual(nums, sorted(nums, reverse=True))


class ChartTest(Base):
    def test_activity_series(self):
        import datetime as dt
        with self.app.app_context():
            from crm import stats as S
            ids = [self.pid("Берг")]
            r = S.activity_series(ids, dt.date(2026, 11, 1), dt.date(2026, 11, 30))
            self.assertEqual(r["mode"], "day")
            self.assertEqual(len(r["labels"]), 30)
            self.assertEqual([s["key"] for s in r["series"]],
                             ["new_contacts", "first", "analysis", "consult", "closing", "deals"])
            y = S.activity_series(ids, dt.date(2026, 1, 1), dt.date(2026, 12, 31))
            self.assertEqual(y["mode"], "week")
            future = S.activity_series(ids, dt.date(2031, 1, 1), dt.date(2031, 1, 10))
            self.assertTrue(all(v is None for v in future["series"][0]["values"]))
        c = self.client_for("admin@demo.local")
        self.assertIn(b'data-chart=', c.get("/stats?period=year&scope=team").data)


class MigrationTest(unittest.TestCase):
    def test_old_database_gets_new_columns(self):
        import sqlite3
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "old.sqlite3")
        db = sqlite3.connect(path)
        db.execute("CREATE TABLE deals (id INTEGER PRIMARY KEY, contact_id INTEGER, date TEXT, product TEXT, ke REAL, note TEXT, created_at TEXT)")
        db.commit()
        db.close()
        old_db, old_inst = os.environ.get("CRM_DB"), os.environ.get("CRM_INSTANCE")
        os.environ["CRM_DB"], os.environ["CRM_INSTANCE"] = path, os.path.join(tmp, "inst")
        try:
            from crm import create_app
            create_app()
            cols = [r[1] for r in sqlite3.connect(path).execute("PRAGMA table_info(deals)")]
            self.assertIn("source", cols)
        finally:
            for k, v in (("CRM_DB", old_db), ("CRM_INSTANCE", old_inst)):
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
