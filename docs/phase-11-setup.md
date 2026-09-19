# Phase 11: n8n integration

## What this phase adds

Your agent was a brain that could only be reached through the Streamlit page,
and when it handed a case to a human, nobody was told. Now:

| Piece | What it does |
|---|---|
| **Agent API** (`api/server.py`) | The agent as a small web service on `http://127.0.0.1:8000`. n8n (and WhatsApp in Phase 12) talk to the agent through it. **No new answering logic:** it calls the same `handle_message()` as the chat page, so routing, database answers, the answer checker, memory, escalations and logging all behave exactly as tested in Phase 10. |
| **Workflow 1: Chat webhook** | Any app sends a customer message to n8n and gets the agent's reply back. Phase 12 plugs WhatsApp in here. |
| **Workflow 2: Escalation alerts** | Every minute: new cases are **emailed** to you (Gmail), including a case that becomes **more urgent** (e.g. "I want a human" then "I have a rash"). |
| **Workflow 3: Daily summary** | An email every morning at 9:00 (Karachi time): yesterday's chats, where answers came from, new/open cases, and the questions the agent couldn't answer. |
| **Workflow 4: Overdue reminders** | Every 30 min: a reminder email for any HIGH case waiting over 2 h, or NORMAL case over 24 h (the policy promises 1 business day). |

Python stays the brain (every decision is tested); n8n is the wiring
(messages in and out, alerts, schedules).

### How alerts can't get lost or repeated
n8n asks the API for alerts that haven't been sent, emails them, and only
**then** marks them sent. If Gmail, n8n or your internet fails in between,
the alert simply comes again next minute: late, never lost. A sent alert
never repeats, unless the case became more urgent.

### What the alerts look like
```
Subject: [GlowCare] 🔴 New case ESC-45 (HIGH): possible skin reaction / safety concern

🔴 New case ESC-45: HIGH priority
Reason: possible skin reaction / safety concern
Customer wrote: I got a rash after using the cleanser
Chat #212 · n8n · 20 Sep 10:15
Reply to the customer, then mark it resolved:
python -m tools.escalations update ESC-45 resolved
```

## Setup (one time, about 20 minutes)

You'll use **3 PowerShell windows**. Each one starts in your project folder:
```
cd C:\Users\TECHNOSELLERS\Hayyanagent\rag-whatsapp-bot\glowcare-agent
```

### Step 1: Python packages and the database update (window 1)
```
pip install fastapi uvicorn httpx
psql -U postgres -d glowcare -f database\migrations\005_n8n_alerts.sql
```
The migration prints `ALTER TABLE`, `CREATE INDEX`, `DO`. Cases that already
exist are marked as "already announced", so your inbox isn't flooded with old
test cases.

Check everything (free, no AI calls):
```
python -m tests.test_api
python -m tests.test_n8n_workflows
```
Expected: `45/45 passed` and `57/57 passed`.

### Step 2: Start the agent API (window 1, keep it open)
```
python -m api.server
```
Wait for `Uvicorn running on http://127.0.0.1:8000`. Open
<http://127.0.0.1:8000/docs> in your browser to see every endpoint (you can
try `/chat` there with "Try it out").

### Step 3: Install Node.js 24 and n8n (window 2)
1. Download **Node.js 24 LTS** (Windows Installer .msi) from <https://nodejs.org>
   and install it with the default options. n8n 2.x needs Node **24 or newer**.
   Close and reopen PowerShell, then check:
   ```
   node --version
   ```
   It must say `v24.` something.
2. Install n8n (the exact version these workflows were tested with; takes a few minutes):
   ```
   npm install -g n8n@2.39.8
   ```
   If PowerShell says *"running scripts is disabled on this system"*, run this once, then repeat the install:
   ```
   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
   ```

### Step 4: Import the 4 workflows, then start n8n (window 2)
From the `glowcare-agent` folder, while n8n is **not** running:
```
n8n import:workflow --separate --input=n8n
```
Expected: `Successfully imported 4 workflows.` (Importing again later replaces
the same 4 workflows, it never makes duplicates.) Then start n8n and keep this window open:
```
n8n start
```
Open <http://localhost:5678>. The first time, n8n asks you to create an owner
account (email + password): it stays on your computer. You'll see the 4
GlowCare workflows. (A warning about "running n8n outside a container" is
harmless.)

### Step 5: Make a Gmail app password
n8n sends the alerts from your Gmail account. Gmail doesn't accept your
normal password from apps, so you make a separate **app password**:
1. Open <https://myaccount.google.com/security> and make sure
   **2-Step Verification** is **On** (Google only offers app passwords then).
2. Open <https://myaccount.google.com/apppasswords>, type the name `n8n`,
   click **Create**. Google shows a 16-letter password like `abcd efgh ijkl mnop`.
   Copy it (without the spaces). Treat it like an API key: it can send email
   as you. You can delete it on the same page any time.

(If the App passwords page says it isn't available, e.g. on a school or
work account, use a personal Gmail account instead.)

### Step 6: Connect Gmail in n8n
1. Open **GlowCare 2 - Escalation alerts by email**. Double-click **Send email**
   → **Credential to connect with** → **Create new credential** and fill in:

   | Field | Value |
   |---|---|
   | User | your Gmail address |
   | Password | the 16-letter app password (no spaces) |
   | Host | `smtp.gmail.com` |
   | Port | `465` |
   | SSL/TLS | **on** |

   Click **Save** (n8n tests the connection: it should say it worked). Close the node.
2. Double-click **Config** and fill in:
   - **email_from**: your Gmail address (the same as in the credential)
   - **email_to**: who receives the alerts (your Gmail again, or a teammate's address)
3. Press **Ctrl+S** (save), then click **Publish** (top right).
4. Do the same in **GlowCare 3** and **GlowCare 4**: in **Send email** pick the
   credential you just made (don't create a new one), fill in **email_from** and
   **email_to** in **Config**, save, **Publish**.
5. Open **GlowCare 1 - Chat webhook** and click **Publish** (nothing to edit).

> **Important:** after ANY change to a published workflow, click **Publish**
> again. n8n keeps running the last published version until you do.

If you set `GLOWCARE_API_KEY` in `.env` (optional, see Security), also put the
same value in **api_key** in all 4 Config nodes, then restart `python -m api.server`.

## Test it (window 3)

**1. A question through n8n:**
```
$body = @{ message = "How much is the Niacinamide Serum?"; session_id = "test-1" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:5678/webhook/glowcare-chat -ContentType "application/json" -Body $body
```
Expected: `ok: True`, `reply: The Niacinamide Serum costs $19.99.`

**2. Memory (same session_id = same chat):**
```
$body = @{ message = "Is it in stock?"; session_id = "test-1" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:5678/webhook/glowcare-chat -ContentType "application/json" -Body $body
```
Expected: the stock of the **Niacinamide Serum**, same `conversation_id` as before.

**3. An escalation → alert email within a minute:**
```
$body = @{ message = "I got a rash after using the cleanser"; session_id = "test-2" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:5678/webhook/glowcare-chat -ContentType "application/json" -Body $body
```
Expected: `escalated: True` and a reference `ESC-…`; within about a minute an email
arrives: **[GlowCare] 🔴 New case ESC-… (HIGH)**. (First time: check the Spam folder
and mark it "Not spam".)

**4. Upgrade alert:**
```
$body = @{ message = "I want to talk to a human"; session_id = "test-3" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:5678/webhook/glowcare-chat -ContentType "application/json" -Body $body
```
Wait for the 🟡 NORMAL email, then:
```
$body = @{ message = "Also my skin is burning now"; session_id = "test-3" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:5678/webhook/glowcare-chat -ContentType "application/json" -Body $body
```
Expected: **🔴 ESC-… is now HIGH priority (was normal)**, same case number, no duplicate case.

**5. Daily summary now:** open **GlowCare 3** and click **Execute workflow**.
The summary email arrives.

**6. See it on the dashboard:** `python -m streamlit run frontend/dashboard.py --server.port 8502`
→ the Channel filter now has **n8n**.

Clean up the test cases afterwards:
```
python -m tools.escalations list
python -m tools.escalations update ESC-<number> resolved
```

## Every day
Start 2 windows (plus the chat page/dashboard if you want them):
```
python -m api.server
n8n start
```
If `python -m api.server` isn't running, the webhook answers with a polite
"technical problem" reply (HTTP 503) and alerts wait until it's back.

## Settings (.env, all optional)
| Setting | Default | Meaning |
|---|---|---|
| `GLOWCARE_API_KEY` | empty | If set, every API call must send it (put it in each Config node's `api_key`) |
| `ALERT_MIN_PRIORITY` | `normal` | Instant alerts for this priority and above. `low` = "I don't have that information" cases (they're in the daily summary anyway) |
| `OVERDUE_HOURS_HIGH` / `_NORMAL` | `2` / `24` | When a waiting case gets a reminder (and how often it repeats) |
| `SESSION_HOURS` | `24` | A message after this many quiet hours starts a new chat |
| `API_PORT` | `8000` | If you change it, change `api_url` in the Config nodes too |

Change the daily summary time in workflow 3's **Every day at 9:00** node.

## Security
- The **Gmail app password** lives only in n8n's credential store (encrypted),
  never in a file. Don't paste it into Config, a chat, or a screenshot. If it
  ever leaks, delete it at myaccount.google.com/apppasswords and make a new one.
- The API listens on **127.0.0.1**: only programs on your computer can reach
  it. In Phase 12, n8n is what faces the internet, never this API.
- `.env` and the n8n data folder (`C:\Users\<you>\.n8n`) hold secrets: never
  share or upload them.
- Demo and test chats never create alerts and aren't in the daily summary.

## Troubleshooting
| You see | Fix |
|---|---|
| `Your Node.js version ... is currently not supported by n8n` | Install Node.js 24 LTS (Step 3), reopen PowerShell |
| `npm install` fails with `gyp ERR!` | You're not on Node 24: n8n's ready-made parts exist only for Node 24+. Check `node --version` |
| `n8n : The term 'n8n' is not recognized` | Close and reopen PowerShell after installing |
| Webhook reply `ok: False` ... `ECONNREFUSED 127.0.0.1:8000` | Start `python -m api.server` (window 1) |
| ... `401 ... X-API-Key` | `api_key` in Config doesn't match `GLOWCARE_API_KEY` in `.env` |
| Invoke-RestMethod: `404 ... webhook "glowcare-chat" is not registered` | Workflow 1 isn't published: open it, click **Publish** |
| No alert email | Check Spam first. Then n8n → **Executions** tab of workflow 2: a red run says why. `Invalid login` / `Username and Password not accepted` = use the **app password**, not your normal one; `ETIMEDOUT` = port must be 465 with SSL/TLS on |
| `No recipients defined` | email_to in Config is empty |
| Changed something but nothing changed | Click **Publish** again |
| Old test cases keep sending overdue reminders | Resolve them: `python -m tools.escalations update ESC-<n> resolved` |

## What was tested before delivery
- `tests/test_api.py` (45 checks): replies, chats continued by session_id,
  memory through the API, 24-hour chat window, alerts sent exactly once,
  upgrade alerts, an upgrade that happens *while* an alert is being sent,
  low-priority and demo cases not alerting, overdue timing and repeat,
  daily report, escaping of customer text (`<b>`, `&`), bad input, agent
  errors, the API key, and every alert being email-ready (subject + HTML).
- `tests/test_n8n_workflows.py` (57 checks): every workflow file is valid,
  every connection is real, every API call exists with the right method, no
  password inside any file.
- The 4 workflows were run for real in **n8n 2.39.8** (Node 24) against the
  API, with a stand-in for Gmail's mail server (login required, like Gmail):
  webhook replies and memory, 400 on an empty message, 503 when the API is
  down or the key is wrong, new/upgrade alert emails, **a mail server outage
  (alert delivered after it came back, failed run shown in red)**, the daily
  summary and an overdue reminder.
