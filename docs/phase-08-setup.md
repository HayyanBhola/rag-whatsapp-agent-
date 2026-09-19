# Phase 8 — Conversation Memory + Logging

## What this phase adds

### 1. Every message is saved
Each customer message and each reply is stored in the `messages` table,
with the full audit trail for the reply:
- route and reason (database / knowledge / clarify / escalate / greeting)
- the database rows used, or the document sections + what the AI wrote +
  why the checker rejected it
- the escalation it created or joined
- the memory note, if earlier messages changed the answer

Review any chat from the command line (the Phase 9 dashboard will show the same):
```
python -m tools.conversations            # recent chats
python -m tools.conversations 7          # chat #7, message by message
python -m tools.conversations 7 --why    # ...with the reason for each reply
```

### 2. The agent remembers the last few messages
| Customer says | Before Phase 8 | Now |
|---|---|---|
| "How much does it cost?" → "Hydra Balance Moisturizer" | product description | **$24.99** |
| "How much is the serum?" → "Is it in stock?" | asked which product | **serum is out of stock** |
| "How much is the serum?" → "And the sunscreen?" | product description | **sunscreen price $21.00** |
| "Where is my order?" → "GC10241" | (already worked) | shipped |

**How it's built, and why:** memory is a few plain rules in `agent/memory.py`,
not "send the whole chat to the AI". Memory only decides *which product* and
*which question*; the facts still come only from the database, so the
Phase 5 guarantees don't change. The rules only look back 3 replies, and
when there's no product to refer to, the agent still asks.

Memory never overrides safety: "I got a rash from it" is always an escalation.
Memory never turns a policy question into a product lookup: after "how much
is the serum?", "and the sunscreen, can I return it?" goes to the return
policy, not the sunscreen's price.

Also fixed in the router: "Is the serum available for international
shipping?" is a shipping question now, not a stock lookup. "Available"
only counts as a stock word when no shipping/return/refund/cancel word is
in the message. (New test sheet case: `kb-availability-shipping`.)

"It" only refers back to a product if the chat hasn't moved on: after
"How much is the cleanser?" -> "Where is my order GC10241?", the question
"How much is it?" asks which product instead of assuming the cleanser.

"Clear chat" now marks the old chat 'closed' (escalated chats stay
'escalated'), so the Phase 9 dashboard can count open vs finished chats.

## Setup (one time)

From the `glowcare-agent` folder:
```
psql -U postgres -d glowcare -f database/migrations/003_message_logging.sql
```
Expected: four `ALTER TABLE` lines and `CREATE INDEX`. Safe to run twice.

## Test it

1. Automatic checks (no AI calls, free, clean up after themselves):
   ```
   python -m tests.test_memory
   python -m tests.test_escalations
   ```
   Expected: `33/33 passed` and `15/15 passed`.

2. In the chat page (`python -m streamlit run frontend/app.py`), click
   **Clear chat**, then type one at a time:
   - `How much does it cost?` → asks which product
   - `Hydra Balance Moisturizer` → $24.99, with the note *Used earlier messages: ...*
   - `Is it in stock?` → in stock
   - `And the sunscreen?` → in stock (only 8 left)

3. Look at that chat as the team would:
   ```
   python -m tools.conversations
   python -m tools.conversations <chat number> --why
   ```

## Files

- `database/migrations/003_message_logging.sql`: adds `source`, `answer_type`,
  `details` (JSON), `escalation_id` to `messages`, plus an index.
- `database/db.py`: `log_message`, `get_recent_turns`, `get_conversation_messages`,
  `list_conversations`.
- `agent/memory.py`: the three memory rules + the log row format.
- `agent/support_agent.py`: `handle_message` loads recent messages, applies
  memory, and logs the exchange (only when a `conversation_id` is given, so the
  test sheet still never writes to the database).
- `agent/router.py`: keeps the question type on document questions too, so
  memory can tell "what ingredients does it have?" is an ingredients question.
- `tools/conversations.py`: the chat viewer.
- `frontend/app.py`: shows the memory note under a reply; "Clear chat" closes
  the old conversation.
- `tests/eval_cases.json`: 26 cases (adds the "available for shipping" case).
- `tests/test_memory.py`: 33 checks. `tests/test_escalations.py`: now also
  cleans up logged messages.

## Not in this phase

- Refreshing the browser starts a new chat on screen (earlier chats are still
  saved and viewable with the tool). Reopening old chats in the page: Phase 9.
- Policy questions are still answered one at a time: "can I return **it**?" is
  answered from the return policy in general, which is correct for GlowCare's
  policies because they don't differ by product.
