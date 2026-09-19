"""
tests/test_api.py

Checks the Phase 11 API (api/server.py) against your REAL database, the way
n8n uses it: chat messages in, replies out, chats continued by session_id,
escalation alerts sent exactly once (and again only if a case gets more
urgent), overdue reminders, the daily report, and the API key.

The questions used never reach the AI (prices, stock, escalations), so this
costs nothing. Everything it creates is deleted at the end.

    python -m tests.test_api
"""

import re
import sys
from unittest import mock

from fastapi.testclient import TestClient

from api import server
from database import db, notifications as nt

CHANNEL = "apitest"  # a channel only this test uses
checks = []
created = set()
client = TestClient(server.app)


def check(name, condition, detail=""):
    checks.append(bool(condition))
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not condition else ""))


def chat(message, session=None, **extra):
    body = {"message": message, "channel": CHANNEL, **extra}
    if session:
        body["session_id"] = session
    r = client.post("/chat", json=body)
    data = r.json()
    if r.status_code == 200 and data.get("conversation_id"):
        created.add(data["conversation_id"])
    return r.status_code, data


def sql(query, params=()):
    with db.get_connection() as conn, conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall() if cur.description else None
        conn.commit()
        return rows


def pending_ids():
    return {a["escalation_id"]: a for a in client.get("/alerts/escalations?limit=100").json()["alerts"]}


def overdue_ids():
    return {r["escalation_id"]: r for r in client.get("/alerts/overdue?limit=100").json()["reminders"]}


def html_ok(text):
    """Only the tags we write ourselves (<b>, <code>) and nothing else that
    looks like a tag: customer text must be escaped."""
    stripped = re.sub(r"</?(b|code)>", "", text)
    return "<" not in stripped and ">" not in stripped


def email_ok(item):
    """Email-ready: a subject line (no line breaks) and an HTML body."""
    return (item.get("subject", "").startswith("[GlowCare]") and "\n" not in item["subject"]
            and "<br>" in item.get("html", "") and "<script" not in item["html"].lower())


def cleanup():
    ids = list(created) + [r["conversation_id"] for r in
                           sql("SELECT conversation_id FROM conversations WHERE channel = %s", (CHANNEL,))]
    sql("DELETE FROM messages WHERE conversation_id = ANY(%s)", (ids,))
    sql("DELETE FROM escalations WHERE conversation_id = ANY(%s)", (ids,))
    sql("DELETE FROM conversations WHERE conversation_id = ANY(%s)", (ids,))
    return len(set(ids))


def main():
    try:
        # 1. Health
        h = client.get("/health").json()
        check("/health: API up and database reachable", h["status"] == "ok" and h["database"] == "ok", h)

        # 2. A one-off question: answered from the database, chat closed after.
        code, r = chat("How much is the Niacinamide Serum?")
        check("/chat answers a price question from the database",
              code == 200 and r["ok"] and r["route"] == "database" and "$" in r["reply"], r)
        status = sql("SELECT status FROM conversations WHERE conversation_id = %s", (r["conversation_id"],))
        check("one-off question (no session_id): chat is closed afterwards", status[0]["status"] == "closed")
        channel = sql("SELECT channel FROM conversations WHERE conversation_id = %s", (r["conversation_id"],))
        check("the chat is saved under its channel", channel[0]["channel"] == CHANNEL)

        # 3. Same session_id -> same chat, and memory works across messages.
        _, a = chat("How much is the Niacinamide Serum?", session="cust-1")
        _, b = chat("Is it in stock?", session="cust-1")
        check("same session_id continues the same chat",
              a["conversation_id"] == b["conversation_id"] and a["new_chat"] and not b["new_chat"])
        check("memory works through the API ('it' = the serum)",
              b["route"] == "database" and "Niacinamide" in b["reply"] and b["memory"], b)
        _, c = chat("Hello", session="cust-2")
        check("a different session_id gets its own chat", c["conversation_id"] != a["conversation_id"])
        msgs = sql("SELECT COUNT(*) AS n FROM messages WHERE conversation_id = %s", (a["conversation_id"],))
        check("every message is logged (2 questions + 2 replies)", msgs[0]["n"] == 4, msgs)

        # 4. After 24 h of silence, or once closed, a new chat starts.
        sql("UPDATE messages SET created_at = created_at - INTERVAL '25 hours' WHERE conversation_id = %s",
            (a["conversation_id"],))
        sql("UPDATE conversations SET started_at = started_at - INTERVAL '25 hours' WHERE conversation_id = %s",
            (a["conversation_id"],))
        _, d = chat("Hi again", session="cust-1")
        check("more than 24 h later: a new chat", d["conversation_id"] != a["conversation_id"] and d["new_chat"])
        db.close_conversation(d["conversation_id"])
        _, e = chat("Hello?", session="cust-1")
        check("after the chat was closed: a new chat", e["conversation_id"] != d["conversation_id"])

        # 5. Escalation -> alert for the team, sent exactly once.
        _, r = chat("I got a rash after using the <b>cleanser</b> & it burns", session="cust-3")
        esc = r["escalation"]
        check("skin reaction: escalated as HIGH with a reference in the reply",
              r["escalated"] and esc and esc["priority"] == "high" and esc["reference"] in r["reply"], r)
        pending = pending_ids()
        alert = pending.get(esc["id"])
        check("new case appears in /alerts/escalations", alert is not None)
        check("alert text names the case, priority and reason",
              alert and esc["reference"] in alert["text"] and "HIGH" in alert["text"]
              and "skin reaction" in alert["text"], alert and alert["text"])
        check("customer text is escaped (can't break the alert's HTML)",
              alert and html_ok(alert["text"]) and "&lt;b&gt;cleanser" in alert["text"],
              alert and alert["text"])
        check("alert is email-ready: subject with case + priority, HTML body",
              alert and email_ok(alert) and esc["reference"] in alert["subject"] and "HIGH" in alert["subject"]
              and "&lt;b&gt;cleanser" in alert["html"], alert and (alert.get("subject"), alert.get("html")))
        ok = client.post(f"/alerts/escalations/{esc['id']}/sent", json={"priority": "high"})
        check("n8n marks it sent", ok.status_code == 200)
        check("a sent alert is not offered again", esc["id"] not in pending_ids())
        _, r2 = chat("Hello? The rash is still there", session="cust-3")
        check("same chat reports again: no duplicate case, no new alert",
              r2["escalation"] and r2["escalation"]["id"] == esc["id"] and esc["id"] not in pending_ids(), r2)

        # 6. A case that becomes MORE urgent is announced again.
        _, h1 = chat("I want to talk to a human", session="cust-4")
        hid = h1["escalation"]["id"]
        check("human request: NORMAL priority alert", pending_ids().get(hid, {}).get("priority") == "normal")
        client.post(f"/alerts/escalations/{hid}/sent", json={"priority": "normal"})
        _, h2 = chat("Also my face is swollen and itchy after the serum", session="cust-4")
        up = pending_ids().get(hid)
        check("upgraded to HIGH -> alerted again, marked as an upgrade",
              h2["escalation"]["priority"] == "high" and up and up["upgraded"]
              and "is now HIGH" in up["text"] and "is now HIGH" in up["subject"], up)

        # 7. Race: the case is upgraded while n8n is sending the old alert.
        _, s1 = chat("Can I speak to a real person?", session="cust-5")
        sid = s1["escalation"]["id"]
        seen = pending_ids()[sid]["priority"]                     # n8n reads "normal"
        chat("I have a burning feeling on my skin", session="cust-5")  # upgraded meanwhile
        client.post(f"/alerts/escalations/{sid}/sent", json={"priority": seen})  # n8n acks "normal"
        check("upgrade during sending is not lost (still pending as HIGH)",
              pending_ids().get(sid, {}).get("priority") == "high")

        # 8. Low priority ("I don't have that") waits for the daily summary.
        _, low = chat("Do you have a loyalty rewards program?", session="cust-6")
        if low.get("escalation"):
            check("low-priority case gives no instant alert (daily summary instead)",
                  low["escalation"]["priority"] == "low" and low["escalation"]["id"] not in pending_ids())
        else:
            check("low-priority case gives no instant alert (answered, nothing to alert)", True)

        # 9. Demo/test chats never alert.
        demo_chat = db.create_conversation(channel="demo")
        created.add(demo_chat)
        demo_esc = db.create_escalation(demo_chat, "customer asked for a human", "high", "demo")
        check("demo chats never alert", demo_esc not in pending_ids())

        # 10. Overdue reminders.
        sql("UPDATE escalations SET created_at = NOW() - INTERVAL '3 hours' WHERE escalation_id = %s", (esc["id"],))
        sql("UPDATE escalations SET created_at = NOW() - INTERVAL '3 hours' WHERE escalation_id = %s", (hid,))
        overdue = overdue_ids()
        check("HIGH case waiting 3 h (> 2 h target) is overdue", esc["id"] in overdue,
              list(overdue))
        check("reminder text says how long it has waited",
              esc["id"] in overdue and "Overdue" in overdue[esc["id"]]["text"]
              and "3.0 h" in overdue[esc["id"]]["text"] and html_ok(overdue[esc["id"]]["text"]),
              overdue.get(esc["id"], {}).get("text"))
        check("reminder is email-ready", esc["id"] in overdue and email_ok(overdue[esc["id"]])
              and "Overdue" in overdue[esc["id"]]["subject"])
        _, n1 = chat("Please let me talk to an agent", session="cust-7")
        sql("UPDATE escalations SET created_at = NOW() - INTERVAL '3 hours' WHERE escalation_id = %s",
            (n1["escalation"]["id"],))
        check("NORMAL case waiting 3 h (< 24 h target) is not overdue", n1["escalation"]["id"] not in overdue_ids())
        client.post(f"/alerts/overdue/{esc['id']}/sent")
        check("after a reminder: not reminded again straight away", esc["id"] not in overdue_ids())
        sql("UPDATE escalations SET reminded_at = NOW() - INTERVAL '3 hours' WHERE escalation_id = %s", (esc["id"],))
        check("still open 2 h after the reminder: reminded again", esc["id"] in overdue_ids())
        db.update_escalation(esc["id"], "resolved")
        check("resolved cases get no alerts or reminders",
              esc["id"] not in overdue_ids() and esc["id"] not in pending_ids())

        # 11. Daily report.
        rep = client.get("/reports/daily").json()
        check("daily report has the summary text",
              "GlowCare daily summary" in rep["text"] and "Chats:" in rep["text"], rep["text"][:200])
        check("daily report leaves out demo/test chats", "demo" not in rep["channels"]
              and CHANNEL in rep["channels"], rep["channels"])
        check("daily report counts this test's chats", (rep["stats"].get("questions") or 0) >= 10,
              rep["stats"])
        check("daily report is valid HTML and email-ready", html_ok(rep["text"]) and email_ok(rep))

        # 12. Bad input is refused clearly.
        check("empty message -> 422", client.post("/chat", json={"message": "   "}).status_code == 422)
        check("reserved channel 'demo' -> 422",
              client.post("/chat", json={"message": "hi", "channel": "demo"}).status_code == 422)
        check("invalid channel name -> 422",
              client.post("/chat", json={"message": "hi", "channel": "Bad Channel!"}).status_code == 422)
        check("unknown conversation_id -> 404",
              client.post("/chat", json={"message": "hi", "conversation_id": 99999999}).status_code == 404)
        check("unknown escalation -> 404",
              client.post("/alerts/escalations/99999999/sent", json={"priority": "high"}).status_code == 404)
        check("bad priority -> 422",
              client.post(f"/alerts/escalations/{hid}/sent", json={"priority": "urgent"}).status_code == 422)

        # 13. If the agent crashes, the customer still gets a polite reply.
        with mock.patch("agent.support_agent.handle_message", side_effect=RuntimeError("simulated")), \
             mock.patch.object(server.log, "exception"):  # keep the expected error out of the output
            _, broken = chat("How much is the serum?")
        check("agent error -> ok=false and a safe reply, not a crash",
              broken["ok"] is False and broken["reply"] == server.ERROR_REPLY and "simulated" in broken["error"])

        # 14. API key.
        with mock.patch.object(server, "API_KEY", "secret-test-key"):
            no_key = client.post("/chat", json={"message": "hi", "channel": CHANNEL})
            wrong = client.get("/alerts/escalations", headers={"X-API-Key": "nope"})
            right = client.get("/alerts/escalations", headers={"X-API-Key": "secret-test-key"})
            health = client.get("/health")
        check("with GLOWCARE_API_KEY set: no key -> 401", no_key.status_code == 401)
        check("with GLOWCARE_API_KEY set: wrong key -> 401", wrong.status_code == 401)
        check("with GLOWCARE_API_KEY set: right key -> 200", right.status_code == 200)
        check("/health never needs the key", health.status_code == 200)
    finally:
        print(f"(cleaned up {cleanup()} test conversations)")

    passed = sum(checks)
    print("-" * 60)
    print(f"{passed}/{len(checks)} passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
