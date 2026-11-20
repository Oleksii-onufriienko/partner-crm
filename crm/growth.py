"""Рост структуры: воронка партнёров, годовой план, путь до следующей ступени.
Маршруты регистрируются в том же блюпринте «main»."""
import datetime as dt

from flask import abort, flash, g, redirect, render_template, request, url_for

from . import career as K
from . import constants as C
from . import recruit as R
from . import yearplan as Y
from .access import branch_ids, children_map, direct_children, get_person, visible_ids, visible_persons
from .auth import login_required
from .db import execute, query
from .main import _choice, _pid_arg, bp, get_contact
from .util import clean, month_bounds, parse_date, parse_int, safe_next, today


def _scope(pid):
    b = branch_ids(pid)
    scope = "team" if request.args.get("scope") == "team" and len(b) > 1 else "me"
    return scope, b


# ---------------------------------------------------------------- воронка партнёров

@bp.route("/team/candidates", methods=["GET", "POST"])
@login_required
def candidates():
    pid = _pid_arg()
    p = get_person(pid)
    if request.method == "POST":                      # быстро добавить кандидата
        first = clean(request.form.get("first_name"), 80)
        if not first:
            flash("Укажите хотя бы имя.", "error")
        else:
            cid = execute("""INSERT INTO contacts (owner_id, first_name, last_name, phone, profession,
                                                   temperature, channel, partner_interest)
                             VALUES (?, ?, ?, ?, ?, ?, 'warm', 1)""",
                          (pid, first, clean(request.form.get("last_name"), 80), clean(request.form.get("phone"), 40),
                           clean(request.form.get("profession"), 120),
                           _choice(request.form.get("temperature"), C.TEMPERATURES, "warm")))
            R.set_stage(query("SELECT * FROM contacts WHERE id = ?", (cid,), one=True), "interest", g.user["id"])
            flash(f"{first} добавлен(а) в кандидаты.", "ok")
        return redirect(url_for("main.candidates", person=pid, scope=request.args.get("scope", "me")))

    scope, b = _scope(pid)
    owners = b if scope == "team" else [pid]
    rows = R.candidates(owners)
    columns = {k: [] for k in C.keys(C.RECRUIT_STAGES)}
    for r in rows:
        columns.setdefault(r["recruit_stage"], []).append(r)
    t = today()
    start = dt.date(t.year, 1, 1)
    year_counts = R.period_counts(owners, start, t)
    month_counts = R.period_counts(owners, month_bounds(t)[0], t)
    reached = R.reached_counts(owners)
    return render_template("candidates.html", p=p, scope=scope, branch_size=len(b), columns=columns,
                           year_counts=year_counts, month_counts=month_counts, reached=reached,
                           total=len(rows), today=t)


@bp.route("/contacts/<int:cid>/recruit", methods=["POST"])
@login_required
def contact_recruit(cid):
    c = get_contact(cid)
    stage = request.form.get("stage")
    back = safe_next(url_for("main.contact", cid=cid))
    if stage == "":
        execute("UPDATE contacts SET recruit_stage = NULL, partner_interest = 0 WHERE id = ?", (cid,))
        flash("Убран из кандидатов.", "ok")
        return redirect(back)
    if stage not in C.keys(C.RECRUIT_STAGES):
        abort(400)
    info = request.form.get("info_date")
    info_date = (parse_date(info).isoformat() if parse_date(info) else "") if info is not None else None
    if stage == "joined" and not c["joined_person_id"]:
        # Сначала заводим человека в структуру — форма уже заполнена данными кандидата
        if info_date is not None:
            execute("UPDATE contacts SET recruit_info_date = ? WHERE id = ?", (info_date or None, cid))
        return redirect(url_for("main.person_new", from_contact=cid))
    R.set_stage(c, stage, g.user["id"], info_date=info_date)
    flash(f"{c['first_name']}: {C.label(C.RECRUIT_STAGES, stage).lower()}.", "ok")
    return redirect(back)


# ---------------------------------------------------------------- годовой план

def _year_arg():
    y = parse_int(request.values.get("year"))
    return y if y and 2000 <= y <= 2100 else today().year


@bp.route("/team/year")
@login_required
def year_plan():
    pid = _pid_arg()
    p = get_person(pid)
    year = _year_arg()
    vp, cmap = visible_persons(), children_map()
    ist = Y.facts(pid, year, vp, cmap)
    ziel = Y.goals(pid, year)
    cols, blocks = Y.view(ist, ziel, year, today())
    totals = {}
    for key in ("eigen", "gruppe", "gesamt", "vm_direct", "vm_indirect", "al_direct", "al_indirect"):
        z = [v for v in ziel[key] if v is not None]
        totals[key] = {"ist": sum(ist[key]), "ziel": sum(z) if z else None}
    return render_template("year_plan.html", p=p, year=year, cols=cols, blocks=blocks, totals=totals,
                           has_team=bool(direct_children(pid)))


@bp.route("/team/year/edit", methods=["GET", "POST"])
@login_required
def year_plan_edit():
    pid = _pid_arg()
    p = get_person(pid)
    year = _year_arg()
    if request.method == "POST":
        Y.save(pid, year, request.form, g.user["id"])
        flash("Годовой план сохранён.", "ok")
        return redirect(url_for("main.year_plan", person=pid, year=year))
    return render_template("year_plan_edit.html", p=p, year=year, ziel=Y.goals(pid, year),
                           metrics=Y.METRICS, blocks=dict(Y.BLOCKS))


# ---------------------------------------------------------------- карьера

def career_rows(root_id):
    vp, cmap = visible_persons(), children_map()
    ids = [i for i in branch_ids(root_id) if vp[i]["active"]]
    facts = K.facts(ids, vp, cmap)
    rows = []
    for i in ids:
        steps = K.plan_for(vp[i], facts[i])
        main_step = max(steps, key=lambda s: s["pct"]) if steps else None
        gap = None
        if main_step:
            crit = main_step["options"][main_step["best"]]
            weakest = min(crit, key=lambda c: c["pct"])
            if not weakest["ok"]:
                gap = weakest
        rows.append({"p": vp[i], "steps": steps, "main": main_step, "gap": gap, "f": facts[i]})
    rows.sort(key=lambda r: (-(r["main"]["pct"] if r["main"] else -1), r["p"]["last_name"]))
    return rows


@bp.route("/team/career")
@login_required
def career():
    pid = _pid_arg()
    p = get_person(pid)
    last = query(f"""SELECT h.*, p.first_name, p.last_name FROM stufe_history h JOIN persons p ON p.id = h.person_id
                     WHERE h.kind = 'promotion' AND h.person_id IN ({','.join('?' * len(branch_ids(pid)))})
                     ORDER BY h.date DESC, h.id DESC LIMIT 10""", branch_ids(pid))
    return render_template("career.html", p=p, rows=career_rows(pid), promotions=last)
