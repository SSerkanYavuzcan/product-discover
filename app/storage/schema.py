CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS products (
    product_id TEXT PRIMARY KEY,
    barcode TEXT,
    gtin TEXT,
    product_name TEXT,
    brand TEXT,
    category TEXT,
    status TEXT NOT NULL,
    confidence_overall REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS product_evidence (
    evidence_id TEXT PRIMARY KEY,
    product_id TEXT,
    source_name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_url TEXT,
    field_name TEXT NOT NULL,
    raw_value TEXT,
    normalized_value TEXT,
    confidence REAL NOT NULL,
    extracted_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS discovery_jobs (
    job_id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL,
    priority TEXT NOT NULL,
    input_type TEXT NOT NULL,
    input_value TEXT NOT NULL,
    batch_id TEXT,
    product_id TEXT,
    source_id TEXT,
    attempt_count INTEGER NOT NULL,
    max_attempts INTEGER NOT NULL,
    error_message TEXT,
    result_product_id TEXT,
    created_at TEXT NOT NULL,
    scheduled_at TEXT,
    started_at TEXT,
    completed_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS batch_jobs (
    batch_id TEXT PRIMARY KEY,
    batch_type TEXT NOT NULL,
    status TEXT NOT NULL,
    filename TEXT,
    total_items INTEGER NOT NULL,
    unique_items INTEGER NOT NULL,
    pending_count INTEGER NOT NULL,
    running_count INTEGER NOT NULL,
    completed_count INTEGER NOT NULL,
    failed_count INTEGER NOT NULL,
    not_found_count INTEGER NOT NULL,
    needs_review_count INTEGER NOT NULL,
    skipped_duplicate_count INTEGER NOT NULL,
    rate_limited_count INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_products_barcode ON products(barcode);
CREATE INDEX IF NOT EXISTS idx_products_gtin ON products(gtin);
CREATE INDEX IF NOT EXISTS idx_discovery_jobs_status ON discovery_jobs(status);
CREATE INDEX IF NOT EXISTS idx_discovery_jobs_batch_id ON discovery_jobs(batch_id);
CREATE INDEX IF NOT EXISTS idx_batch_jobs_status ON batch_jobs(status);
CREATE INDEX IF NOT EXISTS idx_product_evidence_product_id ON product_evidence(product_id);
"""
