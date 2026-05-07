-- Schéma SQLite de l'agent de qualification des incidents SWIFT

CREATE TABLE IF NOT EXISTS incidents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'open',
    priority TEXT,
    category TEXT,
    subcategory TEXT,
    service TEXT,
    reported_by TEXT,
    assigned_to TEXT,
    created_at TEXT,
    updated_at TEXT,
    resolved_at TEXT,
    closed_at TEXT,
    resolution TEXT,
    sla_breach_at TEXT,
    confidence_score REAL,
    is_duplicate INTEGER DEFAULT 0,
    duplicate_of TEXT,
    is_major_incident INTEGER DEFAULT 0,
    qualification_failed INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS incident_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT REFERENCES incidents(id),
    at TEXT,
    action TEXT,
    by TEXT
);

CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY,
    service TEXT,
    severity TEXT,
    name TEXT,
    message TEXT,
    triggered_at TEXT,
    status TEXT,
    runbook_url TEXT,
    labels TEXT   -- JSON sérialisé
);

CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT,
    timestamp TEXT,
    cpu_percent REAL,
    memory_percent REAL,
    error_rate_percent REAL,
    p50_latency_ms INTEGER,
    p99_latency_ms INTEGER,
    requests_per_second REAL,
    custom_metrics TEXT  -- JSON sérialisé
);

CREATE TABLE IF NOT EXISTS services (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE,
    display_name TEXT,
    description TEXT,
    type TEXT,
    language TEXT,
    team TEXT,
    owner TEXT,
    business_criticality TEXT,
    sla_target_availability REAL,
    tier INTEGER,
    dependencies TEXT,  -- JSON array
    dependents TEXT     -- JSON array
);

CREATE TABLE IF NOT EXISTS teams (
    id TEXT PRIMARY KEY,
    name TEXT,
    slack_channel TEXT,
    oncall_email TEXT,
    services TEXT        -- JSON array
);

-- Journal d'audit de toutes les actions de l'agent
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT,
    action TEXT,
    result TEXT,         -- JSON sérialisé
    duration_ms INTEGER,
    model TEXT,
    confidence REAL,
    error TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
