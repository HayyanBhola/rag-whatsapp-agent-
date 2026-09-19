-- Migration 005 (Phase 11): what the n8n workflows need.
-- (FICTIONAL DEMO DATABASE)
--
--   conversations.external_id   who the chat is with on an outside channel
--                               (for n8n now; a WhatsApp number in Phase 12).
--                               Messages with the same channel + external_id
--                               continue the same chat, so memory works there too.
--   escalations.alerted_at        when the team was told about this case (n8n alert)
--   escalations.alerted_priority  the priority the team was told about. If the case
--                                 is upgraded later (e.g. normal -> high), it differs
--                                 from priority and the team is alerted again.
--   escalations.reminded_at       last "this case is overdue" reminder
--
-- Cases that already exist when you run this are marked as already alerted,
-- so switching n8n on doesn't flood your phone with old test cases.
--
-- Safe to run more than once.
--   psql -U postgres -d glowcare -f database/migrations/005_n8n_alerts.sql

ALTER TABLE conversations ADD COLUMN IF NOT EXISTS external_id VARCHAR(100);
CREATE INDEX IF NOT EXISTS idx_conversations_external ON conversations (channel, external_id);

-- The first time only: add the alert columns AND mark the cases that already
-- exist as announced (running the file again must not touch newer cases).
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'escalations' AND column_name = 'alerted_at') THEN
        ALTER TABLE escalations ADD COLUMN alerted_at TIMESTAMP;
        ALTER TABLE escalations ADD COLUMN alerted_priority VARCHAR(10);
        ALTER TABLE escalations ADD COLUMN reminded_at TIMESTAMP;
        UPDATE escalations
        SET alerted_at = created_at, alerted_priority = priority, reminded_at = NOW();
    END IF;
END $$;
