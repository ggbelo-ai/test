-- Conviction Engine — Knowledge Graph Schema
-- Requires: Supabase PostgreSQL with pgvector extension enabled

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- Core entities
-- ============================================================

CREATE TABLE themes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    label TEXT NOT NULL,
    description TEXT,
    novelty_score FLOAT,
    signal_maturity TEXT CHECK (signal_maturity IN (
        'pre_commercial', 'early_commercial', 'accelerating', 'crowded'
    )),
    status TEXT CHECK (status IN ('emerging', 'active', 'crowded')) DEFAULT 'emerging',
    signal_sources JSONB DEFAULT '[]'::jsonb,
    embedding VECTOR(1536),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    url TEXT,
    stage TEXT,
    sector TEXT,
    geography TEXT,
    founded_date DATE,
    source TEXT CHECK (source IN ('yc', 'opencorporates', 'tracxn', 'edgar', 'manual')),
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE founders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    linkedin_url TEXT,
    twitter_handle TEXT,
    github_username TEXT,
    signal_score INT DEFAULT 0,
    signals_detected TEXT[] DEFAULT '{}',
    partner_decision TEXT CHECK (partner_decision IN ('reach_out', 'watching', 'pass')),
    draft_outreach TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- Junction tables (relationships / graph edges)
-- ============================================================

CREATE TABLE founder_founded_company (
    founder_id UUID NOT NULL REFERENCES founders(id) ON DELETE CASCADE,
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    role TEXT DEFAULT 'founder',
    PRIMARY KEY (founder_id, company_id)
);

CREATE TABLE company_operates_in_theme (
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    theme_id UUID NOT NULL REFERENCES themes(id) ON DELETE CASCADE,
    relevance_score FLOAT DEFAULT 1.0,
    PRIMARY KEY (company_id, theme_id)
);

CREATE TABLE theme_related_to_theme (
    theme_id_a UUID NOT NULL REFERENCES themes(id) ON DELETE CASCADE,
    theme_id_b UUID NOT NULL REFERENCES themes(id) ON DELETE CASCADE,
    similarity_score FLOAT NOT NULL,
    PRIMARY KEY (theme_id_a, theme_id_b),
    CHECK (theme_id_a <> theme_id_b)
);

CREATE TABLE founder_expert_in_theme (
    founder_id UUID NOT NULL REFERENCES founders(id) ON DELETE CASCADE,
    theme_id UUID NOT NULL REFERENCES themes(id) ON DELETE CASCADE,
    confidence FLOAT DEFAULT 1.0,
    PRIMARY KEY (founder_id, theme_id)
);

-- ============================================================
-- Living Investment Memo (singleton document store)
-- ============================================================

CREATE TABLE living_memo (
    id INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),  -- singleton row
    memo JSONB NOT NULL DEFAULT '{
        "last_updated": null,
        "active_theses": [],
        "watch_list_founders": []
    }'::jsonb,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Insert the singleton row
INSERT INTO living_memo (id, memo) VALUES (1, '{
    "last_updated": null,
    "active_theses": [],
    "watch_list_founders": []
}'::jsonb)
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- Indexes for performance
-- ============================================================

-- Vector similarity search on theme embeddings
CREATE INDEX idx_themes_embedding ON themes
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 10);

-- Text search indexes
CREATE INDEX idx_themes_label ON themes USING gin (to_tsvector('english', label));
CREATE INDEX idx_companies_name ON companies USING gin (to_tsvector('english', name));
CREATE INDEX idx_founders_name ON founders USING gin (to_tsvector('english', name));

-- Status/maturity filters
CREATE INDEX idx_themes_status ON themes (status);
CREATE INDEX idx_themes_signal_maturity ON themes (signal_maturity);
CREATE INDEX idx_founders_signal_score ON founders (signal_score DESC);
CREATE INDEX idx_founders_partner_decision ON founders (partner_decision);

-- Timestamp indexes for recent-first queries
CREATE INDEX idx_themes_created_at ON themes (created_at DESC);
CREATE INDEX idx_companies_created_at ON companies (created_at DESC);
CREATE INDEX idx_founders_created_at ON founders (created_at DESC);

-- ============================================================
-- Updated-at trigger
-- ============================================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER themes_updated_at
    BEFORE UPDATE ON themes
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER companies_updated_at
    BEFORE UPDATE ON companies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER founders_updated_at
    BEFORE UPDATE ON founders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER living_memo_updated_at
    BEFORE UPDATE ON living_memo
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
