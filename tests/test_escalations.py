"""
tests/test_escalations.py

Checks Phase 7 against your REAL database: that hand-offs create escalation
records, never duplicates, and upgrade priority when things get more urgent.
Uses no AI calls (costs nothing). Everything it creates is deleted at the end.

    python -m tests.test_escalations
"""

import sys

from database import db
from agent.support_agent import handle_message

checks = []


def check(name, condition, detail=""):
    checks.append(condition)
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not condition else ""))


def count_escalations(conversation_id):
    with db.get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM escalations WHERE conversation_id = %s", (conversation_id,))
        return cur.fetchone()["n"]


def cleanup(conversation_ids):
    with db.get_connection() as conn, conn.cursor() as cur:
        # messages point at escalations (Phase 8), so they go first
        cur.execute("DELETE FROM messages WHERE conversation_id = ANY(%s)", (conversation_ids,))
        cur.execute("DELETE FROM escalations WHERE conversation_id = ANY(%s)", (conversation_ids,))
        cur.execute("DELETE FROM conversations WHERE conversation_id = ANY(%s)", (conversation_ids,))
        conn.commit()


def main():
    created = []
    try:
        # 1. Asking for a human creates ONE record with a reference in the reply.
        chat = db.create_conversation(); created.append(chat)
        r = handle_message("I want to talk to a human", conversation_id=chat, verbose=False)
        ref = f"ESC-{r['escalation_id']}"
        check("human request creates an escalation", r["escalation_id"] is not None and r["escalation_new"])
        check("reply contains the reference number", ref in r["answer"], r["answer"])
        row = db.get_open_escalation(chat)
        check("record saved with priority 'normal' and the customer's message",
              row and row["priority"] == "normal" and row["customer_message"] == "I want to talk to a human",
              str(row))

        # 2. Asking again in the same chat does NOT create a duplicate.
        r2 = handle_message("please let me speak to a real person", conversation_id=chat, verbose=False)
        check("second request reuses the same case", r2["escalation_id"] == r["escalation_id"]
              and not r2["escalation_new"] and ref in r2["answer"], r2["answer"])
        check("still exactly 1 record in this chat", count_escalations(chat) == 1)

        # 3. A more urgent follow-up upgrades the SAME case to high priority.
        r3 = handle_message("I got a rash after using the cleanser", conversation_id=chat, verbose=False)
        row = db.get_open_escalation(chat)
        check("safety follow-up upgrades priority to 'high'",
              r3["escalation_id"] == r["escalation_id"] and row["priority"] == "high", str(row))
        check("upgraded record keeps both customer messages",
              "rash" in row["customer_message"] and "human" in row["customer_message"])

        # 4. Conversation is marked escalated.
        with db.get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT status FROM conversations WHERE conversation_id = %s", (chat,))
            check("conversation status is 'escalated'", cur.fetchone()["status"] == "escalated")

        # 5. Staff resolve it -> the next hand-off in that chat opens a NEW case.
        db.update_escalation(r["escalation_id"], "resolved", "Test: resolved by staff")
        resolved = [e for e in db.list_escalations("resolved") if e["escalation_id"] == r["escalation_id"]]
        check("staff can resolve with a note",
              resolved and resolved[0]["resolved_at"] and resolved[0]["staff_notes"] == "Test: resolved by staff")
        r4 = handle_message("This is terrible, I want to complain", conversation_id=chat, verbose=False)
        check("after resolving, a new hand-off opens a new case",
              r4["escalation_new"] and r4["escalation_id"] != r["escalation_id"])

        # 6. A fresh chat with a safety issue starts as 'high' directly.
        chat2 = db.create_conversation(); created.append(chat2)
        r5 = handle_message("my face is burning after the sunscreen", conversation_id=chat2, verbose=False)
        check("safety issue in a new chat is created as 'high'",
              r5["escalation_new"] and db.get_open_escalation(chat2)["priority"] == "high")

        # 6b. One message with BOTH a human request and a rash -> high, safety reply.
        chat3 = db.create_conversation(); created.append(chat3)
        r8 = handle_message("I want to talk to a human, I got a rash after using the cleanser",
                            conversation_id=chat3, verbose=False)
        check("human request + rash in one message is 'high' priority",
              r8["escalation_reason"] == "possible skin reaction / safety concern"
              and db.get_open_escalation(chat3)["priority"] == "high", r8["escalation_reason"])

        # 7. Without a conversation_id (how the test sheet runs) nothing is saved.
        r6 = handle_message("I want to talk to a human", verbose=False)
        check("no conversation_id -> no record, no reference in reply",
              r6["escalate"] and r6["escalation_id"] is None and "ESC-" not in r6["answer"])

        # 8. Normal questions never escalate.
        r7 = handle_message("How much is the Hydra Balance Moisturizer?", conversation_id=chat2, verbose=False)
        check("price question does not escalate", not r7["escalate"] and r7["escalation_id"] is None)

        # 9. Bad status is rejected.
        try:
            db.update_escalation(r5["escalation_id"], "done")
            check("invalid status is rejected", False)
        except ValueError:
            check("invalid status is rejected", True)
    finally:
        cleanup(created)
        print(f"(cleaned up {len(created)} test conversations)")

    passed = sum(checks)
    print("-" * 60)
    print(f"{passed}/{len(checks)} passed")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
