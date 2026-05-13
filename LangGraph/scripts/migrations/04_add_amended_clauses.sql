ALTER TABLE temporal_metadata
  ADD COLUMN IF NOT EXISTS amended_clauses JSONB;

CREATE INDEX IF NOT EXISTS idx_temporal_amended_clauses
  ON temporal_metadata USING GIN(amended_clauses);
