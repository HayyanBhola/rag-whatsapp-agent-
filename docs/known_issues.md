# Known issues

Bugs found but not fixed yet. Each one gets a case in the evaluation golden
set (`tests/eval_cases.json`) before it is fixed, so the fix can be proven.

## 1. Greeting variants are routed to the knowledge base and escalated

**Found:** 2026-10-12, while running `tests/test_api.py` (section 4 used
"Hi again" and the chat unexpectedly stayed open).

**Issue:** Some greetings don't match the router's greeting rule
(`GREETING_PATTERN` in `agent/router.py`), so they fall through to the
`knowledge` route. The knowledge base has no answer, the reply is
`not_found`, and the support policy then escalates the chat as
"information not available" (low priority).

Checked with `route_message()` on 2026-10-12:

| Message        | Route       |
|----------------|-------------|
| `Hi`           | greeting    |
| `Hey`          | greeting    |
| `Hello?`       | greeting    |
| `good morning` | greeting    |
| `Hi again`     | knowledge ✗ |
| `hello again`  | knowledge ✗ |
| `hey there`    | knowledge ✗ |
| `hi there`     | knowledge ✗ |

**Impact:**
- An unnecessary human escalation: a case lands in the team's queue (and the
  daily summary) for a customer who only said hello.
- A confusing reply: the customer is told "I don't have that information"
  and given a reference number instead of a greeting.
- An escalated chat is never auto-closed, so the customer's next message
  continues that chat instead of starting a fresh one.

**Status:** Not fixed yet. To be added to the evaluation golden set and then
fixed in the router. `tests/test_api.py` now uses "Hi" for its
conversation-handling check, because that check tests sessions, not greeting
routing.
