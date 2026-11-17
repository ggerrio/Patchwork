-- Patchwork Initial Database Schema (PostgreSQL 15+ with pgvector)

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'incident_status') THEN
        CREATE TYPE incident_status AS ENUM (
            'QUEUED',
            'INVESTIGATING',
            'PATCHING',
            'VERIFYING',
            'AWAITING_APPROVAL',
            'APPROVED_PR_OPENED',
            'REJECTED',
            'FAILED_MAX_RETRIES',
            'ESCALATED_TO_HUMAN'
        );
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS incidents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    fingerprint VARCHAR(64) NOT NULL,
    repo_owner VARCHAR(255) NOT NULL,
    repo_name VARCHAR(255) NOT NULL,
    base_branch VARCHAR(100) DEFAULT 'main',
    error_type VARCHAR(255) NOT NULL,
    error_message TEXT NOT NULL,
    stack_trace TEXT NOT NULL,
    status incident_status DEFAULT 'QUEUED',
    proposed_diff TEXT,
    patch_explanation TEXT,
    pr_url TEXT,
    retry_count INT DEFAULT 0,
    total_tokens INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_traces (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id UUID REFERENCES incidents(id) ON DELETE CASCADE,
    step_name VARCHAR(100) NOT NULL,
    thought_summary TEXT NOT NULL,
    tool_output TEXT,
    tokens_used INT DEFAULT 0,
    latency_ms INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS code_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    repo_full_name VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    symbol_name VARCHAR(255),
    chunk_type VARCHAR(50), -- 'function' | 'class'
    content TEXT NOT NULL,
    embedding vector(768), -- Compatible with Gemini text-embedding-004
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_incidents_fingerprint ON incidents(fingerprint);
CREATE INDEX IF NOT EXISTS idx_agent_traces_incident_id ON agent_traces(incident_id);
CREATE INDEX IF NOT EXISTS idx_code_chunks_repo_full_name ON code_chunks(repo_full_name);
CREATE INDEX IF NOT EXISTS idx_code_chunks_embedding ON code_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

