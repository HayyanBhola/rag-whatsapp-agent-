-- Migration 003 (Phase 8): log every chat message with its audit trail.
-- (FICTIONAL DEMO DATABASE)
--
-- The messages table already exists (sender, content, intent). This adds
-- what's needed to review a conversation later and answer "why did the
-- assistant say that?" (Section 14 of the brief):
--   source         database | knowledge_base | fixed_reply (assistant rows)
--   answer_type    llm | quoted_source | not_found (knowledge-base answers)
--   details        route, product/order recognised, DB rows or document
--                  chunks used, what the AI wrote, why the checker rejected it
--   escalation_id  the escalation this reply created or joined, if any
--
-- Safe to run more than once.
--   psql -U postgres -d glowcare -f database/migrations/003_message_logging.sql

ALTER TABLE messages ADD COLUMN IF NOT EXISTS source VARCHAR(20);
ALTER TABLE messages ADD COLUMN IF NOT EXISTS answer_type VARCHAR(20);
ALTER TABLE messages ADD COLUMN IF NOT EXISTS details JSONB;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS escalation_id INTEGER REFERENCES escalations(escalation_id);

-- Loading "the last few messages of this chat" happens on every message,
-- so make that lookup fast.
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages (conversation_id, message_id);
