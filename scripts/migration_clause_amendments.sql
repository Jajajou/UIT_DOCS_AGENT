-- Clause-level amendment tracking
-- Run once before reindex.

-- Resolved clause-level links (both docs indexed, link confirmed)
CREATE TABLE IF NOT EXISTS clause_amendments (
    id                  SERIAL PRIMARY KEY,
    workspace           VARCHAR(255) NOT NULL DEFAULT 'default',

    -- Amending document
    source_doc_number   VARCHAR(100) NOT NULL,
    source_clause_id    VARCHAR(50),   -- e.g. "Điều 1"; NULL = whole doc

    -- Amended document
    target_doc_number   VARCHAR(100) NOT NULL,
    target_clause_id    VARCHAR(50),   -- e.g. "Điều 5"; NULL = whole doc

    -- Type: replace_full | replace_partial | supplement | repeal
    amendment_type      VARCHAR(50)  NOT NULL DEFAULT 'replace_partial',

    -- Denormalized doc_ids for fast Qdrant lookups
    source_doc_id       VARCHAR(255),
    target_doc_id       VARCHAR(255),

    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ca_target_doc
    ON clause_amendments (workspace, target_doc_number);

CREATE INDEX IF NOT EXISTS idx_ca_target_doc_clause
    ON clause_amendments (workspace, target_doc_number, target_clause_id);

CREATE INDEX IF NOT EXISTS idx_ca_source_doc
    ON clause_amendments (workspace, source_doc_number);

CREATE INDEX IF NOT EXISTS idx_ca_target_doc_id
    ON clause_amendments (target_doc_id);

-- Pending links: source indexed but target not yet in DB
CREATE TABLE IF NOT EXISTS pending_amendments (
    id                  SERIAL PRIMARY KEY,
    workspace           VARCHAR(255) NOT NULL DEFAULT 'default',

    source_doc_number   VARCHAR(100) NOT NULL,
    source_clause_id    VARCHAR(50),
    target_doc_number   VARCHAR(100) NOT NULL,
    target_clause_id    VARCHAR(50),
    amendment_type      VARCHAR(50)  NOT NULL DEFAULT 'replace_partial',
    source_doc_id       VARCHAR(255),

    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pa_target_doc
    ON pending_amendments (workspace, target_doc_number);
