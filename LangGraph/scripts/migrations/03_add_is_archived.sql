-- Migration: Add is_archived columns to temporal_metadata
-- Run once via: psql -h localhost -p 5433 -U <user> -d lightrag -f add_is_archived_migration.sql

ALTER TABLE temporal_metadata
  ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP,
  ADD COLUMN IF NOT EXISTS archive_reason VARCHAR(100);

CREATE INDEX IF NOT EXISTS idx_temporal_is_archived
  ON temporal_metadata(is_archived);

CREATE INDEX IF NOT EXISTS idx_temporal_valid_until_active
  ON temporal_metadata(valid_until)
  WHERE is_archived = FALSE;
