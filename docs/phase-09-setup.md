# Phase 9 — Business / Admin Dashboard

## What this phase adds

A second web page, **for the GlowCare team only**: `frontend/dashboard.py`.
It runs next to the customer chat, on its own address.

| Tab | What the team sees | What they can do |
|---|---|---|
| **Overview** | Chats, questions, % handled without a human, open escalations, average time to resolve, follow-ups understood; questions per day; where answers came from; most-asked-about products; why customers were handed to a human | Pick the period (today / 7 / 30 days / all time) and the channel |
| **Escalations** | Open cases, most urgent first, with priority and status labels, the customer's own words, how long it has waited, and the full chat | Change status (pending → in progress → resolved) and add a dated note |
| **Conversations** | Every saved chat: status, channel, first question, escalation | Search all messages (e.g. `rash`, `GC10241`), filter by status, click a chat to read it with the reason behind each reply |
| **Answer quality** | How many document answers were AI-accepted / quoted instead / not found; the questions the documents couldn't answer (grouped, with counts); every AI answer the checker rejected and why | See exactly what to add to `data/` next |

Design choices:
- **Headline numbers are tiles, not charts.** Every chart is one colour
  with the number printed on each bar, a hover tooltip, and a "Show as table"
  view. Colours are checked for both light and dark mode.
- **"Open escalations" always shows what is waiting right now**, whatever
  period is picked. An old case that's still open still needs someone.
- **Demo data stays separate.** Chats have a `channel` (`web`, `demo`, later
  `whatsapp`), so demo chats never mix with real ones and can be removed.
- **The page only displays.** Every number comes from
  `database/dashboard_queries.py`, and each one is tested against chats with
  known answers.

## Setup (one time)

From the `glowcare-agent` folder:

1. Update the database (adds the `channel` column and two indexes; safe to run twice):
   ```
   psql -U postgres -d glowcare -f database/migrations/004_dashboard.sql
   ```
2. (Recommended) set a dashboard password: add this line to `.env`:
   ```
   DASHBOARD_PASSWORD=choose-something
   ```
   Without it, anyone who can open the page can read customer chats. That's
   fine on your own computer; set one before showing it to anyone else.
3. (Optional) add realistic sample chats so the dashboard has data to show.
   They go through the real agent. It costs $0 on Gemini's free tier, and
   takes about a minute because of the free tier's speed limit:
   ```
   python -m tools.demo_data
   ```
   No AI at all: `python -m tools.demo_data --no-ai`.
   Remove them later: `python -m tools.demo_data --remove`.

## Run it

```
python -m streamlit run frontend/dashboard.py --server.port 8502
```
It opens at http://localhost:8502. The customer chat keeps running at
http://localhost:8501 in another PowerShell window, and both can be open at once.

## Test it

```
python -m tests.test_dashboard
```
Expected: `43/43 passed`. It builds a small set of test chats with known
answers (channel `test`), checks every dashboard number, opens the page
headless and saves an escalation through its form, then deletes the test
chats. No AI calls. Your real and demo chats are not touched.

Manual check:
1. Overview → the numbers match what you chatted.
2. Escalations → set one case to **In progress** with a note → **Save** →
   the note appears with today's date.
3. Conversations → search `rash` → click the chat → open **Why this reply**.
4. Answer quality → the questions the documents couldn't answer are listed.

## Files

- `database/migrations/004_dashboard.sql`: `conversations.channel` plus indexes.
- `database/dashboard_queries.py`: every dashboard number (read-only).
- `database/db.py`: `create_conversation(..., channel="web")`.
- `frontend/dashboard.py`: the page.
- `tools/demo_data.py`: sample chats (`--no-ai`, `--remove`).
- `tests/test_dashboard.py`: 43 checks (numbers + page).
- `.env.example`: `DASHBOARD_PASSWORD`.
- `requirements.txt`: `streamlit>=1.64` (the dashboard uses newer Streamlit features).

## Not in this phase

- One shared password, no individual staff accounts. Real logins and roles
  would come with a production deployment.
- No automatic alerts to staff when a high-priority case arrives. That fits
  n8n in **Phase 11** (e.g. email/Slack on every high-priority escalation).
- `tools/escalations.py` and `tools/conversations.py` still work. The dashboard
  does the same things with a screen.
