"""
database/notifications.py

Queries behind the n8n workflows (Phase 11): which escalations the team
still has to be told about, which cases are overdue, and marking them as
sent. Kept apart from db.py (the agent's tools) and dashboard_queries.py
(read-only numbers), because these functions also WRITE: they remember
what was already sent, so nobody gets the same alert twice.

How "sent" works (the outbox pattern): n8n asks for the pending alerts,
sends each one by email, and only THEN marks it sent. If the email or
n8n fails half-way, the unsent alerts are simply offered again next time,
so an alert can be late but never lost.
"""

import os

from dotenv import load_dotenv

from database.db import get_connection

load_dotenv()

# Channels that are never real customers: no alerts, not in the daily report.
INTERNAL_CHANNELS = ("demo", "test")

PRIORITY_RANK = {"low": 0, "normal": 1, "high": 2}

# Lowest priority that gets an instant alert. "low" = the agent didn't have
# the information: those are listed in the daily summary instead of
# emailing you about every off-topic question.
ALERT_MIN_PRIORITY = os.getenv("ALERT_MIN_PRIORITY", "normal").strip().lower()
if ALERT_MIN_PRIORITY not in PRIORITY_RANK:
    ALERT_MIN_PRIORITY = "normal"

# How long a case may wait before a reminder, in hours. The support policy
# promises a human reply "within 1 business day"; a possible skin reaction
# shouldn't wait that long.
OVERDUE_HOURS = {
    "high": float(os.getenv("OVERDUE_HOURS_HIGH", "2")),
    "normal": float(os.getenv("OVERDUE_HOURS_NORMAL", "24")),
}


def _all(query, params=()):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return [dict(r) for r in cur.fetchall()]


def _alert_priorities():
    rank = PRIORITY_RANK[ALERT_MIN_PRIORITY]
    return [p for p, r in PRIORITY_RANK.items() if r >= rank]


def pending_escalation_alerts(limit: int = 20) -> list:
    """Open cases the team hasn't been told about yet, or that became MORE
    urgent after the last alert (alerted_priority differs from priority).
    Most urgent first."""
    return _all("""
        SELECT e.escalation_id, e.conversation_id, e.reason, e.priority, e.status,
               e.customer_message, e.created_at, e.alerted_priority, c.channel
        FROM escalations e
        JOIN conversations c ON c.conversation_id = e.conversation_id
        WHERE e.status <> 'resolved'
          AND e.priority = ANY(%s)
          AND c.channel <> ALL(%s)
          AND (e.alerted_at IS NULL OR e.alerted_priority IS DISTINCT FROM e.priority)
        ORDER BY CASE e.priority WHEN 'high' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END,
                 e.created_at
        LIMIT %s;
    """, (_alert_priorities(), list(INTERNAL_CHANNELS), limit))


def mark_escalation_alerted(escalation_id: int, priority: str) -> bool:
    """Records that the team was told about this case AT this priority.
    `priority` is the one that was in the alert, not the current one: if the
    case was upgraded while the alert was being sent, the upgrade is still
    announced next time. Returns False if the case doesn't exist."""
    if priority not in PRIORITY_RANK:
        raise ValueError(f"priority must be one of {tuple(PRIORITY_RANK)}, got {priority!r}")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE escalations SET alerted_at = NOW(), alerted_priority = %s
                WHERE escalation_id = %s RETURNING escalation_id;
            """, (priority, escalation_id))
            found = cur.fetchone() is not None
            conn.commit()
            return found


def overdue_escalations(limit: int = 20) -> list:
    """Open high/normal cases that have waited longer than OVERDUE_HOURS and
    haven't had a reminder within that same time. So a case is reminded
    about at most once per OVERDUE_HOURS (every 2 h for high by default)."""
    return _all("""
        SELECT e.escalation_id, e.conversation_id, e.reason, e.priority, e.status,
               e.customer_message, e.created_at, e.reminded_at, c.channel,
               ROUND((EXTRACT(EPOCH FROM (NOW() - e.created_at)) / 3600)::numeric, 1) AS hours_waiting,
               t.hours AS target_hours
        FROM escalations e
        JOIN conversations c ON c.conversation_id = e.conversation_id
        JOIN (VALUES ('high', %s::float), ('normal', %s::float)) AS t(priority, hours)
             ON t.priority = e.priority
        WHERE e.status <> 'resolved'
          AND c.channel <> ALL(%s)
          AND e.created_at < NOW() - make_interval(secs => t.hours * 3600)
          AND (e.reminded_at IS NULL OR e.reminded_at < NOW() - make_interval(secs => t.hours * 3600))
        ORDER BY CASE e.priority WHEN 'high' THEN 0 ELSE 1 END, e.created_at
        LIMIT %s;
    """, (OVERDUE_HOURS["high"], OVERDUE_HOURS["normal"], list(INTERNAL_CHANNELS), limit))


def mark_reminded(escalation_id: int) -> bool:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE escalations SET reminded_at = NOW() WHERE escalation_id = %s "
                        "RETURNING escalation_id;", (escalation_id,))
            found = cur.fetchone() is not None
            conn.commit()
            return found


def customer_channels() -> list:
    """Channels with real customers (everything except demo/test)."""
    return [r["channel"] for r in _all(
        "SELECT DISTINCT channel FROM conversations WHERE channel <> ALL(%s) ORDER BY channel;",
        (list(INTERNAL_CHANNELS),))]


# --- Conversations from outside channels -----------------------------------

# A message more than this many hours after the last one starts a new chat
# (24 h, like WhatsApp's customer-service window).
SESSION_HOURS = float(os.getenv("SESSION_HOURS", "24"))


def find_or_create_conversation(channel: str, external_id: str) -> tuple:
    """The chat to continue for this sender on this channel: the newest one
    that isn't closed and had activity within SESSION_HOURS. Otherwise a new
    chat is started. Returns (conversation_id, is_new)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT c.conversation_id
                FROM conversations c
                LEFT JOIN LATERAL (SELECT MAX(created_at) AS last_at FROM messages m
                                   WHERE m.conversation_id = c.conversation_id) m ON TRUE
                WHERE c.channel = %s AND c.external_id = %s AND c.status <> 'closed'
                  AND COALESCE(m.last_at, c.started_at) >= NOW() - make_interval(secs => %s)
                ORDER BY c.conversation_id DESC LIMIT 1;
            """, (channel, external_id, SESSION_HOURS * 3600))
            row = cur.fetchone()
            if row:
                return row["conversation_id"], False
            cur.execute("INSERT INTO conversations (channel, external_id) VALUES (%s, %s) "
                        "RETURNING conversation_id;", (channel, external_id))
            conversation_id = cur.fetchone()["conversation_id"]
            conn.commit()
            return conversation_id, True


def conversation_exists(conversation_id: int) -> bool:
    return bool(_all("SELECT 1 FROM conversations WHERE conversation_id = %s;", (conversation_id,)))
