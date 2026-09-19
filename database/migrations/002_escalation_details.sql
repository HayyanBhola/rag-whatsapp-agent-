-- Migration 002 (Phase 7): what a human team member needs to act on an
-- escalation. (FICTIONAL DEMO DATABASE)
--
--   priority          high = possible skin reaction (handle first)
--                     normal = asked for a human / complaint
--                     low = the assistant didn't have the information
--   customer_message  the exact message that triggered the hand-off
--   staff_notes       what the team member did (filled in by staff)
--   resolved_at       when it was closed
--
-- Safe to run more than once.
--   psql -U postgres -d glowcare -f database/migrations/002_escalation_details.sql

ALTER TABLE escalations ADD COLUMN IF NOT EXISTS priority VARCHAR(10) NOT NULL DEFAULT 'normal';
ALTER TABLE escalations ADD COLUMN IF NOT EXISTS customer_message TEXT;
ALTER TABLE escalations ADD COLUMN IF NOT EXISTS staff_notes TEXT;
ALTER TABLE escalations ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP;
