"""Права доступа по дереву структуры.

Правило: человек видит себя и всех, кто ниже него в структуре (на любую глубину).
Администратор видит всех. Менять структурные данные (ступень, коэффициент,
наставника, доступ) может только тот, кто выше — или администратор."""

from flask import abort, g

from .db import query


def subtree_ids(root_id):
    rows = query(
        """WITH RECURSIVE sub(id) AS (
               SELECT ?
               UNION
               SELECT p.id FROM persons p JOIN sub ON p.parent_id = sub.id
           ) SELECT id FROM sub""",
        (root_id,),
    )
    return [r["id"] for r in rows]


def visible_persons():
    """dict id -> row всех видимых пользователю людей (кэш на запрос)."""
    if "vis_persons" not in g:
        if g.user["is_admin"]:
            rows = query("SELECT * FROM persons")
        else:
            ids = subtree_ids(g.user["id"])
            marks = ",".join("?" * len(ids))
            rows = query(f"SELECT * FROM persons WHERE id IN ({marks})", ids)
        g.vis_persons = {r["id"]: r for r in rows}
    return g.vis_persons


def visible_ids():
    return set(visible_persons().keys())


def get_person(pid):
    p = visible_persons().get(pid)
    if p is None:
        abort(404)
    return p


def can_manage(person):
    """Может ли текущий пользователь менять структурные данные человека."""
    if g.user["is_admin"]:
        return True
    return person["id"] != g.user["id"] and person["id"] in visible_ids()


def children_map():
    if "children_map" not in g:
        persons = visible_persons()
        cmap = {}
        for p in persons.values():
            cmap.setdefault(p["parent_id"], []).append(p)
        for lst in cmap.values():
            lst.sort(key=lambda r: (not r["active"], r["last_name"].lower(), r["first_name"].lower()))
        g.children_map = cmap
    return g.children_map


def roots():
    """Верхние узлы дерева для текущего пользователя."""
    if g.user["is_admin"]:
        persons = visible_persons()
        rs = [p for p in persons.values() if p["parent_id"] is None or p["parent_id"] not in persons]
        rs.sort(key=lambda r: (r["id"] != g.user["id"], r["last_name"].lower()))
        return rs
    return [visible_persons()[g.user["id"]]]


def branch_ids(pid):
    """id человека и всех его людей ниже (в пределах видимого)."""
    cmap = children_map()
    out, stack = [], [pid]
    while stack:
        cur = stack.pop()
        out.append(cur)
        stack.extend(c["id"] for c in cmap.get(cur, []))
    return out


def tree_rows():
    """Плоский список (person, depth) в порядке обхода дерева — для таблиц и select."""
    cmap = children_map()
    out = []

    def walk(p, depth):
        out.append((p, depth))
        for c in cmap.get(p["id"], []):
            walk(c, depth + 1)

    for r in roots():
        walk(r, 0)
    return out


def person_options(active_only=True):
    return [(p, d) for p, d in tree_rows() if p["active"] or not active_only]


def direct_children(pid):
    return children_map().get(pid, [])


def has_team(pid):
    return bool(children_map().get(pid))
