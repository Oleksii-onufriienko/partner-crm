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
                    f"/stats?person={self.pid('Ланге')}&scope=team"]:
            r = c.get(url)
            self.assertEqual(r.status_code, 200, url)
            self.assertNotIn(b"Traceback", r.data)

    def test_pages_render_for_vm_without_team(self):
        c = self.client_for("oleg@demo.local")
        for url in ["/", "/team", "/contacts", "/planner", "/stats", "/account", "/meetings/new", "/contacts/new"]:
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


if __name__ == "__main__":
    unittest.main()
