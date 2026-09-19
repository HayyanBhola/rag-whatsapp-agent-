# Phase 7 — Human Escalation

## What this phase adds

When the agent hands a customer to a human, it now **saves a real escalation
record** in PostgreSQL, gives the customer a reference number, and lets the
team work through the cases.

| Trigger | Priority | Example |
|---|---|---|
| Possible skin reaction / safety concern | **high** | "I got a rash after using the cleanser" |
| Customer asks for a human | normal | "I want to talk to a human" |
| Complaint | normal | "This is the worst service" |
| The assistant didn't have the information | low | "Do you have a loyalty program?" (when not in the documents) |

Rules (from `data/policies/customer_support_policy.md` and SYSTEM_RULES rule 9):
- The customer gets a reference: *"Your reference number is ESC-12."*
- **One open case per chat.** Asking for a human twice gives the same reference,
  not a duplicate record.
- **Urgency only goes up.** If a chat that's already escalated reports a skin
  reaction, the same case is upgraded to *high* and both messages are kept.
- After staff **resolve** a case, a new hand-off in that chat opens a new case.
- If saving fails (database down), the customer still gets a reply, **without**
  a reference number, and is told to contact support directly. A reference is
  never shown unless it was actually saved.
- The test sheet (`run_eval`) never creates records: it runs without a chat.

What changed:
- `database/migrations/002_escalation_details.sql` — adds `priority`,
  `customer_message`, `staff_notes`, `resolved_at` to `escalations`.
- `database/db.py` — `create_conversation`, `create_escalation`,
  `get_open_escalation`, `raise_escalation_priority`, `list_escalations`,
  `update_escalation`.
- `agent/support_agent.py` — `handle_message(message, conversation_id=...)`
  saves the escalation and adds the reference to the reply.
- `frontend/app.py` — each browser chat is one conversation row; the yellow
  notice shows the reference and priority.
- `tools/escalations.py` — command-line tool for the team (until the Phase 9
  dashboard).
- `tests/test_escalations.py` — 14 checks against your real database.

## Setup (one time)

From the `glowcare-agent` folder:
```
psql -U postgres -d glowcare -f database/migrations/002_escalation_details.sql
```
Expected: four lines of `ALTER TABLE`. Safe to run twice.

## Test it

1. Automatic checks (no AI calls, costs nothing, cleans up after itself):
   ```
   python -m tests.test_escalations
   ```
   Expected: `14/14 passed`.

2. In the chat page (`python -m streamlit run frontend/app.py`):
   - "I want to talk to a human" → reply ends with *Your reference number is ESC-…*
   - Then "I got a rash after using the cleanser" → *I've marked your case ESC-… as urgent*
   - Sidebar shows *Conversation #…*; "Clear chat" starts a new one.

3. See the cases as a team member would:
   ```
   python -m tools.escalations
   ```
   Work on one:
   ```
   python -m tools.escalations update ESC-3 in_progress
   python -m tools.escalations update ESC-3 resolved "Called customer, sent replacement"
   ```
   `python -m tools.escalations all` also shows resolved cases.

## Not in this phase

- Chat messages themselves aren't saved yet, only the escalations and the
  conversation row. Full message logging and conversation memory: **Phase 8**.
- The team works cases from the command line. A web dashboard: **Phase 9**.
- No notifications (email/WhatsApp) to staff yet; that fits with n8n in **Phase 11**.
