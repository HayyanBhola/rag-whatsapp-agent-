-- Migration 004 (Phase 9): what the admin dashboard needs.
-- (FICTIONAL DEMO DATABASE)
--
--   conversations.channel   where a chat came from:
--                           'web'  = the Streamlit chat page (default)
--                           'demo' = sample chats added by tools/demo_data.py
--                           later: 'whatsapp' (Phase 12)
--                           The dashboard can show one channel at a time,
--                           so demo chats never get mixed up with real ones.
--   index on messages(created_at)  the dashboard filters by date a lot.
--
-- Safe to run more than once.
--   psql -U postgres -d glowcare -f database/migrations/004_dashboard.sql

ALTER TABLE conversations ADD COLUMN IF NOT EXISTS channel VARCHAR(20) NOT NULL DEFAULT 'web';
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages (created_at);
CREATE INDEX IF NOT EXISTS idx_conversations_channel ON conversations (channel);
