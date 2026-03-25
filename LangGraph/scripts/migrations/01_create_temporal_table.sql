-- ============================================================
-- Temporal Metadata Table for UIT Documents
-- ============================================================
-- This table stores temporal metadata extracted from UIT documents
-- separately from LightRAG's metadata to avoid conflicts with
-- LightRAG's metadata overwrites during processing.
--
-- Usage:
--   psql -h localhost -p 5433 -U lightrag -d lightrag -f create_temporal_metadata_table.sql
-- ============================================================

-- Drop existing table if exists (for clean reinstall)
DROP TABLE IF EXISTS temporal_metadata CASCADE;

-- Create temporal_metadata table
CREATE TABLE temporal_metadata (
    id SERIAL PRIMARY KEY,

    -- Link to LightRAG documents
    doc_id VARCHAR(255) UNIQUE NOT NULL,  -- LightRAG document ID
    track_id VARCHAR(255),                 -- LightRAG tracking ID
    workspace VARCHAR(255) DEFAULT 'default',  -- LightRAG workspace

    -- Document identification
    document_number VARCHAR(100),          -- e.g., "108/2024/QĐ-ĐHQGTP"
    document_type VARCHAR(100),            -- e.g., "Quyết định", "Thông tư"

    -- Temporal validity
    valid_from DATE,                       -- Document effective date
    valid_until DATE,                      -- Document expiry date (NULL = no expiry)

    -- Student cohorts
    cohort_years JSONB,                    -- Array of years, e.g., [2020, 2021, 2022]
    student_cohorts JSONB,                 -- Alternative field for cohorts

    -- Document relationships
    amends_documents JSONB,                -- Array of document numbers this doc amends
    amended_by_documents JSONB,            -- Array of document numbers that amend this doc

    -- Extraction metadata
    extraction_method VARCHAR(50),         -- "deepseek_ocr", "gemini_ocr", "manual"
    extraction_confidence FLOAT,           -- 0.0 to 1.0
    extraction_timestamp TIMESTAMP,        -- When metadata was extracted

    -- Additional metadata
    additional_metadata JSONB,             -- For any other fields

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for common queries
CREATE INDEX idx_temporal_doc_id ON temporal_metadata(doc_id);
CREATE INDEX idx_temporal_track_id ON temporal_metadata(track_id);
CREATE INDEX idx_temporal_document_number ON temporal_metadata(document_number);
CREATE INDEX idx_temporal_workspace ON temporal_metadata(workspace);
CREATE INDEX idx_temporal_valid_from ON temporal_metadata(valid_from);
CREATE INDEX idx_temporal_valid_until ON temporal_metadata(valid_until);

-- Index for cohort queries (GIN index for JSONB)
CREATE INDEX idx_temporal_cohort_years ON temporal_metadata USING GIN(cohort_years);
CREATE INDEX idx_temporal_student_cohorts ON temporal_metadata USING GIN(student_cohorts);
CREATE INDEX idx_temporal_amends_documents ON temporal_metadata USING GIN(amends_documents);

-- Function to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_temporal_metadata_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update updated_at
CREATE TRIGGER trigger_update_temporal_metadata_timestamp
    BEFORE UPDATE ON temporal_metadata
    FOR EACH ROW
    EXECUTE FUNCTION update_temporal_metadata_timestamp();

-- Grant permissions (adjust user as needed)
GRANT ALL PRIVILEGES ON temporal_metadata TO lightrag;
GRANT USAGE, SELECT ON SEQUENCE temporal_metadata_id_seq TO lightrag;

-- Display table info
\d temporal_metadata

-- Success message
\echo '✓ Temporal metadata table created successfully!'
