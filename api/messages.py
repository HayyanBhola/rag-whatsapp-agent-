"""
api/messages.py

The wording of every alert the n8n workflows send to the team: a subject
line and an HTML body for email (Gmail), plus a "text" version (the same
lines, simple <b>/<code> tags) for chat apps such as Telegram or WhatsApp
later. Written here in Python (not inside n8n) so the wording is in one
place and tested, and the n8n workflows stay simple: they just forward it.

Everything that comes from a customer is HTML-escaped first, so a message
like "<script>" or "a < b" can't break the alert or inject anything.
"""

from datetime import datetime
from html import escape

PRIORITY_ICON = {"high": "🔴", "normal": "🟡", "low": "⚪"}
MAX_QUOTE = 400  # characters of the customer's message shown in an alert


def ref(escalation_id: int) -> str:
    return f"ESC-{escalation_id}"


def _when(value) -> str:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    return value.strftime("%d %b %H:%M") if value else "–"


def _quote(text, limit: int = MAX_QUOTE) -> str:
    """Customer text, shortened FIRST and escaped after (cutting escaped
    text could split "&amp;" and break the HTML)."""
    text = (text or "").strip()
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return escape(text) if text else "–"


def escalation_alert(e: dict) -> str:
    """New case, or a case that became more urgent after it was announced."""
    upgraded = e.get("alerted_priority") and e["alerted_priority"] != e["priority"]
    icon = PRIORITY_ICON.get(e["priority"], "")
    if upgraded:
        title = (f"{icon} <b>{ref(e['escalation_id'])} is now {e['priority'].upper()} priority</b> "
                 f"(was {escape(e['alerted_priority'])})")
    else:
        title = f"{icon} <b>New case {ref(e['escalation_id'])}: {e['priority'].upper()} priority</b>"
    return "\n".join([
        title,
        f"<b>Reason:</b> {escape(e['reason'])}",
        f"<b>Customer wrote:</b> {_quote(e.get('customer_message'))}",
        f"Chat #{e['conversation_id']} · {escape(e['channel'])} · {_when(e['created_at'])}",
        "Reply to the customer, then mark it resolved:",
        f"<code>python -m tools.escalations update {ref(e['escalation_id'])} resolved</code>",
    ])


def overdue_reminder(e: dict) -> str:
    icon = PRIORITY_ICON.get(e["priority"], "")
    return "\n".join([
        f"⏰ {icon} <b>Overdue: {ref(e['escalation_id'])} ({e['priority'].upper()})</b>",
        f"Waiting {e['hours_waiting']} h (target: {e['target_hours']:g} h) · status: {escape(e['status'])}",
        f"<b>Reason:</b> {escape(e['reason'])}",
        f"<b>Customer wrote:</b> {_quote(e.get('customer_message'))}",
        f"Chat #{e['conversation_id']} · {escape(e['channel'])}",
    ])


EMAIL_STYLE = "font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.55;color:#1f1f1f"


def email_html(text: str) -> str:
    """The alert text as an email body. The text is already escaped, so only
    line breaks need converting; <code> gets a monospace look."""
    body = text.replace("\n", "<br>\n").replace(
        "<code>", '<code style="background:#f2f2f2;padding:1px 4px;border-radius:3px">')
    return (f'<div style="{EMAIL_STYLE}">{body}'
            '<p style="color:#777;font-size:12px;margin-top:18px">GlowCare support agent '
            '(fictional demo company) · automatic message</p></div>')


def escalation_subject(e: dict) -> str:
    upgraded = e.get("alerted_priority") and e["alerted_priority"] != e["priority"]
    icon = PRIORITY_ICON.get(e["priority"], "")
    if upgraded:
        return f"[GlowCare] {icon} {ref(e['escalation_id'])} is now {e['priority'].upper()} priority"
    return (f"[GlowCare] {icon} New case {ref(e['escalation_id'])} "
            f"({e['priority'].upper()}): {e['reason']}")


def overdue_subject(e: dict) -> str:
    return (f"[GlowCare] ⏰ Overdue: {ref(e['escalation_id'])} ({e['priority'].upper()}), "
            f"waiting {e['hours_waiting']} h")


def daily_subject(now=None) -> str:
    return f"[GlowCare] 📊 Daily summary, {(now or datetime.now()):%d %b %Y}"


def _pct(part, whole) -> str:
    return f" ({part / whole:.0%})" if whole else ""


def daily_summary(stats: dict, esc: dict, unanswered: list, hours: int, channels: list) -> str:
    """The morning report: yesterday's numbers in a few lines."""
    replies = stats.get("replies") or 0
    lines = [
        f"📊 <b>GlowCare daily summary</b> (last {hours} h)",
        f"Channels: {escape(', '.join(channels)) if channels else 'none yet'}",
        "",
        f"💬 Chats: <b>{stats.get('chats') or 0}</b> · customer messages: <b>{stats.get('questions') or 0}</b>",
    ]
    if replies:
        lines += [
            f"• from the database: {stats.get('from_database') or 0}{_pct(stats.get('from_database') or 0, replies)}",
            f"• from the documents: {stats.get('from_documents') or 0}{_pct(stats.get('from_documents') or 0, replies)}",
            f"• fixed replies (greetings, hand-offs, questions back): {stats.get('fixed_replies') or 0}",
        ]
    kb = (stats.get("ai_accepted") or 0) + (stats.get("ai_quoted") or 0) + (stats.get("not_found") or 0)
    if kb:
        lines.append(f"🤖 Document answers: {stats.get('ai_accepted') or 0} AI-written, "
                     f"{stats.get('ai_quoted') or 0} quoted policy text, "
                     f"{stats.get('not_found') or 0} not found")
    lines += [
        "",
        f"🙋 New escalations: <b>{esc.get('created') or 0}</b>",
        f"📂 Open right now: <b>{esc.get('open_now') or 0}</b>"
        + (f" (🔴 {esc['open_high']} high)" if esc.get("open_high") else ""),
    ]
    if esc.get("avg_resolve_hours") is not None:
        lines.append(f"⏱ Average time to resolve: {esc['avg_resolve_hours']} h")
    if unanswered:
        lines += ["", "❓ <b>Questions the agent couldn't answer:</b>"]
        for u in unanswered:
            times = f" (×{u['times_asked']})" if u.get("times_asked", 1) > 1 else ""
            lines.append(f"• {_quote(u['question'], 150)}{times}")
    if not stats.get("questions"):
        lines += ["", "No customer messages in this period."]
    return "\n".join(lines)
