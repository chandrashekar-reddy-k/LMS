#!/usr/bin/env python3
"""Live-class attendance register and rates. Run from mini-services/lms-api against a running API that
uses the same database (it moves class times into the past directly, so classes count as held)."""
import sys
import uuid
from datetime import datetime, timedelta, timezone

import requests
from sqlalchemy import text

import _testclient  # noqa: F401  (API-client auth mode)
from app.core.database import engine

BASE = "http://127.0.0.1:8000/api"
ok = fail = 0


def check(name, cond, extra=""):
    global ok, fail
    ok, fail = (ok + 1, fail) if cond else (ok, fail + 1)
    print(f"  {'✓' if cond else '✗'} {name} {'' if cond else extra}")


def auth(email, password):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def learner(name):
    em = f"att-{uuid.uuid4().hex[:6]}@test.io"
    r = requests.post(f"{BASE}/auth/register", json={"email": em, "password": "Learner123!", "full_name": name})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, em


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def db(sql, **params):
    with engine.begin() as c:
        c.execute(text(sql), params)


now = datetime.now(timezone.utc)
naive_now = now.replace(tzinfo=None)
S = auth("sarah@infohive.demo", "Teach123!")
J = auth("james@infohive.demo", "Teach123!")

print("== setup ==")
cid = requests.post(f"{BASE}/teach/courses", headers=S, json={"title": f"Attendance course {uuid.uuid4().hex[:4]}"}).json()["id"]
sec = requests.post(f"{BASE}/teach/courses/{cid}/sections", headers=S, json={"title": "Week 1"}).json()
requests.post(f"{BASE}/teach/sections/{sec['id']}/lessons", headers=S, json={"title": "Welcome", "type": "text"})
requests.post(f"{BASE}/teach/courses/{cid}/publish", headers=S)

Ada, ada_email = learner("Ada Present")      # joins both classes
Ben, ben_email = learner("Ben Absent")        # joins neither
Cat, cat_email = learner("Cat Late")          # enrolls after the classes
for h in (Ada, Ben):
    requests.post(f"{BASE}/enrollments/{cid}", headers=h)
# Ada and Ben enrolled a week ago
db("UPDATE enrollments SET enrolled_at = :t WHERE course_id = :c", t=naive_now - timedelta(days=7), c=cid)

s1 = requests.post(f"{BASE}/teach/courses/{cid}/live", headers=S, json={"title": "Week 1 live", "starts_at": iso(now + timedelta(minutes=2)), "duration_minutes": 60}).json()
s2 = requests.post(f"{BASE}/teach/courses/{cid}/live", headers=S, json={"title": "Week 2 live", "starts_at": iso(now + timedelta(minutes=3)), "provider": "external", "external_url": "https://zoom.us/j/999"}).json()
s3 = requests.post(f"{BASE}/teach/courses/{cid}/live", headers=S, json={"title": "Future", "starts_at": iso(now + timedelta(days=3))}).json()
check("classes scheduled", all(x.get("id") for x in (s1, s2, s3)))
for s in (s1, s2):
    check(f"Ada joins {s['title']}", requests.post(f"{BASE}/live/{s['id']}/join", headers=Ada).ok)
# both classes took place 2-3 days ago
db("UPDATE live_sessions SET starts_at = :t WHERE id = :i", t=naive_now - timedelta(days=3), i=s1["id"])
db("UPDATE live_sessions SET starts_at = :t WHERE id = :i", t=naive_now - timedelta(days=2), i=s2["id"])
requests.post(f"{BASE}/enrollments/{cid}", headers=Cat)   # enrolls today, after both classes

print("== course register ==")
r = requests.get(f"{BASE}/teach/courses/{cid}/attendance", headers=S)
reg = r.json()
check("register loads", r.status_code == 200, r.text[:200])
check("only held classes are columns", [s["id"] for s in reg["sessions"]] == [s1["id"], s2["id"]], reg["sessions"])
rows = {l["user"]["email"]: l for l in reg["learners"]}
a, b, c = rows[ada_email], rows[ben_email], rows[cat_email]
check("Ada 2 of 2 = 100%", (a["present"], a["eligible"], a["rate"]) == (2, 2, 100), a)
check("Ada not flagged", not a["at_risk"])
check("Ben 0 of 2 = 0%", (b["present"], b["eligible"], b["rate"]) == (0, 2, 0), b)
check("Ben flagged, missed 2 in a row", b["at_risk"] and b["missed_in_a_row"] == 2, b)
check("late joiner isn't marked absent", c["eligible"] == 0 and c["rate"] is None and not c["at_risk"]
      and all(x["status"] == "not_enrolled" for x in c["cells"]), c)
check("cells say present with join time", a["cells"][0]["status"] == "present" and a["cells"][0]["joined_at"])
check("per-class counts", reg["sessions"][0]["present"] == 1 and reg["sessions"][0]["expected"] == 2, reg["sessions"][0])
check("overall rate", reg["overall_rate"] == 50, reg["overall_rate"])
check("at-risk count", reg["at_risk_count"] == 1)
check("lowest attendance listed first", reg["learners"][0]["user"]["email"] == ben_email)

print("== learner's own rate ==")
m = requests.get(f"{BASE}/courses/{cid}/live/my-attendance", headers=Ada).json()
check("Ada sees 2 of 2", (m["present"], m["eligible"], m["rate"]) == (2, 2, 100), m)
m = requests.get(f"{BASE}/courses/{cid}/live/my-attendance", headers=Cat).json()
check("late joiner sees no classes yet", m["eligible"] == 0 and m["rate"] is None, m)
O, _ = learner("Out Sider")
check("non-enrolled blocked", requests.get(f"{BASE}/courses/{cid}/live/my-attendance", headers=O).status_code == 403)

print("== access ==")
check("other instructor blocked", requests.get(f"{BASE}/teach/courses/{cid}/attendance", headers=J).status_code == 403)
check("learner blocked", requests.get(f"{BASE}/teach/courses/{cid}/attendance", headers=Ada).status_code == 403)
A = auth("admin@infohive.demo", "Admin123!")
check("admin allowed", requests.get(f"{BASE}/teach/courses/{cid}/attendance", headers=A).status_code == 200)

print("== cancelled classes don't count ==")
db("UPDATE live_sessions SET status = 'cancelled' WHERE id = :i", i=s2["id"])
reg = requests.get(f"{BASE}/teach/courses/{cid}/attendance", headers=S).json()
b = next(l for l in reg["learners"] if l["user"]["email"] == ben_email)
check("cancelled class dropped from register", len(reg["sessions"]) == 1 and b["eligible"] == 1, reg["sessions"])

requests.delete(f"{BASE}/teach/courses/{cid}", headers=S)
print("\n" + "=" * 40)
print(f"RESULT: {ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
