# Conviction Engine — Technical Specification v2.0

> Revised: Free data sources · Telegram notifications · Simplified infrastructure

---

## Executive Summary

The **Conviction Engine** is a multi-agent AI system designed to generate alpha in venture capital by identifying emerging market themes, mapping competitive landscapes, and surfacing high-signal founders before consensus forms around investment opportunities.

Unlike existing VC tools that accelerate existing workflows (deal flow management, CRM), this system is designed to compress the time between a market shift emerging and a partner forming a high-conviction investment thesis. It operates autonomously on a daily/weekly cadence, continuously building a proprietary knowledge graph that becomes more valuable over time.

**Core Value Proposition:** A 2-person investment team can operate with the sourcing breadth and pattern recognition of a 10-person firm, while focusing human capital entirely on relationships and conviction calls rather than research prep.

---

## Key Design Principles

### 1. Novelty Over Volume
The system explicitly filters for novel themes (novelty score > 0.70) rather than surfacing every possible signal. This prevents noise and ensures partners only see genuinely early insights.

### 2. Signal Maturity, Not Time Predictions
Rather than predicting hard commercialisation windows (e.g. "18–36 months"), the system classifies each theme by its current **signal maturity** — how far along the academic → open-source → commercial pipeline it sits. This is honest, actionable, and avoids false precision.

### 3. Compounding Knowledge Graph
Every theme explored, every founder tracked, every market mapped enriches the graph. Over time the system develops a proprietary thesis fingerprint — it learns which early signals historically preceded breakout companies in your specific portfolio. This is the moat.

### 4. Human-in-the-Loop at Decision Points
Agents run autonomously for data collection and synthesis. Partners only intervene at decision points: reach out to founder, deep-dive on theme, pass. Telegram inline buttons feed decisions back into the Living Investment Memo without manual data entry.

### 5. Thesis-Driven, Not Deal-Driven
Traditional deal flow systems are reactive: founders reach out, you evaluate. This system is proactive: it discovers where markets are heading, maps the landscape, identifies the best founders — then you reach out when conviction is high.

---

## System Architecture

```
┌─────────────────────────────────────────────────────┐
│                  ORCHESTRATOR AGENT                  │
│    (routing  +  Living Investment Memo  +  Telegram) │
└──────────────┬──────────────┬───────────────┬────────┘
               │              │               │
          [Agent 1]      [Agent 2]       [Agent 3]
          Horizon         Market          Founder
          Scanner       Cartographer      Radar
               │              │               │
               └──────────────┴───────────────┘
                              │
               ┌──────────────▼──────────────┐
               │  KNOWLEDGE GRAPH            │
               │  Supabase (PostgreSQL +     │
               │  pgvector)                  │
               └─────────────────────────────┘
```

### Technology Stack

| Layer | Technology | Notes |
|---|---|---|
| Agent orchestration | LangGraph (Python) | Stateful multi-agent coordination |
| Vector store | pgvector on Supabase | Free — eliminates Pinecone cost |
| Relational DB | Supabase PostgreSQL | Free tier; stores Living Investment Memo |
| Graph queries | Supabase (v1) | Upgrade to Neo4j only once >500 entities |
| Data ingestion | arXiv API, GitHub API, USPTO, pytrends, Playwright | All free |
| Company data | YC company list, OpenCorporates, Tracxn scraping | Replaces paid Crunchbase |
| Job scheduling | Celery + Redis | Daily/weekly agent triggers |
| Notifications | Telegram Bot (`python-telegram-bot`) | Replaces Slack; supports inline decision buttons |

---

## Agent Specifications

### Agent 1 — Horizon Scanner

**Role:** Continuously scans for weak signals in emerging technology and market themes before they appear in startup databases.

**Schedule:** Daily at 06:00 UTC via Celery

**Escalation:** Routes to Orchestrator if `novelty_score > 0.70`

#### Data Sources (all free)
- **arXiv API** — papers in cs.AI, cs.RO, q-bio, eess; tracks citation velocity
- **GitHub API** — repositories gaining >200 stars/week from base <1,000 stars
- **USPTO Patent API** — new filings by technology classification
- **pytrends** (Google Trends) — keyword acceleration curves; free, no API key required

#### Signal Maturity Classification

Rather than predicting commercialisation timelines, each theme receives a `signal_maturity` classification derived from which source layers are firing:

| Maturity Level | Signal Mix |
|---|---|
| `pre_commercial` | arXiv only — academic attention, no product activity |
| `early_commercial` | arXiv + GitHub — researchers building tools, first OSS repos |
| `accelerating` | All sources firing + first companies appearing in YC/OpenCorporates |
| `crowded` | High company count, mainstream press coverage detected |

#### Core Algorithm

1. Fetch signals from each source (last 24 hours)
2. Embed signals using a text embedding model
3. Cluster with HDBSCAN to identify emerging themes
4. Score novelty by comparing each theme against the existing knowledge graph (pgvector cosine similarity)
5. Assign `signal_maturity` based on source mix
6. Route to Orchestrator if `novelty_score > 0.70`

#### Implementation Pseudocode

```python
def scan_horizon():
    signals = []
    signals += fetch_arxiv_papers(last_days=1, citation_velocity_min=10)
    signals += fetch_github_trending(stars_growth_pct_min=30)
    signals += fetch_patent_filings(last_days=7)
    signals += fetch_pytrends_acceleration(keywords=active_theme_labels)

    embeddings = embed_signals(signals)
    themes = cluster_embeddings(embeddings, method="HDBSCAN")

    for theme in themes:
        novelty = compare_to_knowledge_graph(theme)  # pgvector cosine similarity
        maturity = classify_signal_maturity(theme.source_mix)
        if novelty > 0.70:
            orchestrator.route_task("new_theme", theme, maturity)
```

#### Output Schema

```json
{
  "theme_id": "uuid",
  "label": "Neuromorphic edge inference",
  "signal_sources": ["arxiv:2401.xxxxx", "github:org/repo"],
  "novelty_score": 0.84,
  "signal_maturity": "early_commercial",
  "related_existing_theses": ["theme_id_2"]
}
```

---

### Agent 2 — Market Cartographer

**Role:** Takes an emerging theme and builds a structured market map — TAM estimates, competitive landscape segmentation, and incumbent tracking.

**Trigger:** On-demand, called by Orchestrator when a new theme is confirmed as novel.

#### Data Sources (all free)
- **Y Combinator company list** (public) — best free source for early-stage companies by theme
- **OpenCorporates free tier** — company registration data
- **Tracxn free snippets** — scraped via Playwright
- **SEC EDGAR** — S-1 filings for public company comparables and real disclosed revenue figures
- **GitHub organisation count** — number of orgs with repos in the theme as a crowding proxy

#### TAM Estimation Approach

Web-scraped analyst reports produce unreliable, SEO-inflated market size figures. The Cartographer instead uses a bottom-up approach:

1. Find 2–3 public companies in adjacent markets via SEC EDGAR
2. Use their disclosed segment revenues as a proxy for addressable market
3. Cross-reference with company count across YC batches as a market momentum indicator
4. Flag TAM estimate confidence as `low` / `medium` / `high` based on data availability

#### Implementation Pseudocode

```python
def build_market_map(theme):
    companies = scrape_yc_companies(keywords=theme.label, founded_after="2020-01-01")
    companies += search_opencorporates(theme.label)

    public_comps = fetch_edgar_comparables(theme.label)
    tam_estimate = estimate_tam_from_edgar(public_comps)

    competitive_map = {
        "theme_id": theme.id,
        "tam_estimate": tam_estimate,
        "tam_confidence": rate_confidence(public_comps),
        "early_stage": [c for c in companies if c.stage in ["pre-seed", "seed"]],
        "growth_stage": [c for c in companies if c.stage in ["series_a", "series_b"]],
        "incumbents": public_comps
    }

    return competitive_map
```

#### Output

A `MarketMap` record stored in Supabase with JSON arrays for companies by stage, TAM estimates with confidence flags, and public comparables.

---

### Agent 3 — Founder Radar

**Role:** Tracks high-signal founders before they announce a company — monitoring career transitions, research outputs, and behavioural signals.

**Schedule:** Weekly + on-demand when a new theme is created.

**Escalation:** Routes to Orchestrator if `signal_score > 40`

#### Data Sources (all free)
- **Twitter/X API** — bio changes, follower graph, engagement patterns of domain experts
- **GitHub API** — solo contributors to high-growth repositories; new repo creation by tracked individuals
- **Semantic Scholar** — researchers leaving PhD/postdoc positions in relevant fields
- **LinkedIn** (cautious Playwright scraping) — public profile pages only, no authenticated scraping

> **Note on LinkedIn monitoring:** Without Proxycurl, LinkedIn signal quality is reduced. The system compensates by weighting Twitter/X and GitHub signals more heavily. Domain purchase detection has been removed — WHOIS privacy is now standard and produces too many false negatives.

#### Signal Scoring

```python
FOUNDER_SIGNALS = {
    "repeat_founder":                 25,  # Previously exited a company
    "twitter_bio_change_to_stealth":  20,  # Changed bio to "Building something new"
    "ex_tier1_company_departure":     15,  # Left DeepMind, OpenAI, Stripe, etc.
    "published_paper_in_theme":       12,  # Academic authority in the theme
    "open_source_repo_created":       10,  # Started new technical project
    "github_contribution_spike":       8,  # Sudden activity increase on theme repos
}

def score_founder(profile):
    score = sum(FOUNDER_SIGNALS[s] for s in profile.signals if s in FOUNDER_SIGNALS)
    if score > 40:
        orchestrator.escalate_to_telegram(profile, reason="High-signal founder detected")
    return score
```

#### Output Schema

```json
{
  "founder_id": "uuid",
  "name": "Jane Smith",
  "signal_score": 67,
  "signals_detected": ["repeat_founder", "twitter_bio_change_to_stealth"],
  "likely_theme": "theme_id_3",
  "recommended_action": "reach_out_now",
  "draft_outreach": "Hi Jane, noticed you recently left DeepMind..."
}
```

---

### Orchestrator Agent

**Role:** Lightweight coordinator that routes tasks to sub-agents, merges outputs, maintains the Living Investment Memo, and escalates high-conviction findings to partners via Telegram.

#### Escalation Logic
- Theme `novelty_score > 0.75` → send Telegram theme card
- Founder `signal_score > 40` → send Telegram founder card
- Otherwise → log to knowledge graph, continue monitoring

#### System Prompt

```
You are a VC investment orchestrator. You maintain a Living Investment Memo —
a structured JSON document of active theses and tracked founders. When a
sub-agent returns output:
1. Determine if it confirms, extends, or contradicts an existing thesis
2. Update the memo accordingly
3. Classify the signal_maturity of each theme based on source mix
4. If novelty/signal exceeds threshold, send a Telegram alert
Always synthesise into investment-grade language. Never surface raw data.
```

#### Telegram Card Format

Each notification includes inline keyboard buttons that write the partner's decision back to the Living Investment Memo:

| Card Type | Inline Buttons |
|---|---|
| Theme card | 🔍 Deep-dive · 👀 Watch · ❌ Pass |
| Founder card | 📧 Draft outreach · 👀 Watch · ❌ Pass |

---

## Knowledge Graph Schema

Persistent institutional memory layer. Implemented in **Supabase (PostgreSQL + pgvector)** for v1. Migrate to Neo4j AuraDB only when entity count exceeds ~500 and graph traversal queries become a bottleneck.

### Tables

```sql
-- Core entities
CREATE TABLE themes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    label TEXT NOT NULL,
    novelty_score FLOAT,
    signal_maturity TEXT CHECK (signal_maturity IN ('pre_commercial','early_commercial','accelerating','crowded')),
    status TEXT CHECK (status IN ('emerging','active','crowded')),
    embedding VECTOR(1536),  -- pgvector column
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    url TEXT,
    stage TEXT,
    sector TEXT,
    geography TEXT,
    founded_date DATE,
    source TEXT,  -- 'yc', 'opencorporates', 'tracxn'
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE founders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    linkedin_url TEXT,
    twitter_handle TEXT,
    signal_score INT DEFAULT 0,
    signals_detected TEXT[],
    partner_decision TEXT,  -- 'reach_out', 'watching', 'pass'
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Junction tables (relationships)
CREATE TABLE founder_founded_company   (founder_id UUID, company_id UUID);
CREATE TABLE company_operates_in_theme (company_id UUID, theme_id UUID);
CREATE TABLE theme_related_to_theme    (theme_id_a UUID, theme_id_b UUID, similarity_score FLOAT);
CREATE TABLE founder_expert_in_theme   (founder_id UUID, theme_id UUID);
```

### Vector Search (pgvector)

Novelty scoring uses cosine similarity against existing theme embeddings — no separate Pinecone index required:

```sql
SELECT id, label, 1 - (embedding <=> $new_embedding) AS similarity
FROM themes
ORDER BY similarity DESC
LIMIT 5;
```

---

## Living Investment Memo

A structured JSON document stored in Supabase serving as the central state object. Updated continuously by the Orchestrator as agents return outputs.

### Schema

```json
{
  "last_updated": "2026-03-11T06:00:00Z",
  "active_theses": [
    {
      "theme_id": "uuid",
      "label": "Agentic infrastructure for regulated industries",
      "novelty_score": 0.84,
      "signal_maturity": "early_commercial",
      "companies_tracked": 7,
      "watch_list_founders": 3,
      "key_risks": ["EU regulatory uncertainty", "OpenAI competing directly"],
      "status": "emerging"
    }
  ],
  "watch_list_founders": [
    {
      "name": "Jane Smith",
      "signal_score": 67,
      "likely_theme": "uuid",
      "recommended_action": "reach_out_now",
      "partner_decision": "watching"
    }
  ]
}
```

### Update Triggers
- Horizon Scanner discovers new theme → adds to `active_theses`
- Market Cartographer maps companies → updates `companies_tracked`
- Founder Radar scores profile > 40 → adds to `watch_list_founders`
- Partner taps Telegram inline button → updates `partner_decision` field

---

## Operational Workflow

### Daily Cycle (Automated)

| Time (UTC) | Action |
|---|---|
| 06:00 | Horizon Scanner wakes — fetches arXiv, GitHub, USPTO, pytrends signals from last 24h |
| 06:05 | Embeds + clusters signals → HDBSCAN themes → scores novelty via pgvector |
| 06:10 | Themes with novelty > 0.70 routed to Orchestrator |
| 06:12 | Orchestrator triggers Market Cartographer for each novel theme |
| 06:15 | Market Cartographer searches YC list, OpenCorporates, EDGAR → builds MarketMap |
| 06:25 | If novelty > 0.75 → Telegram theme card sent with inline buttons |

### Weekly Cycle (Automated)

| Time (UTC) | Action |
|---|---|
| Mon 08:00 | Founder Radar wakes — scans Twitter/X bios, GitHub repos, Semantic Scholar |
| Mon 08:15 | Scores each profile using signal weights |
| Mon 08:20 | Profiles scoring > 40 routed to Orchestrator |
| Mon 08:25 | Orchestrator matches founder expertise to active theses in Living Investment Memo |
| Mon 08:30 | Generates draft outreach → sends Telegram founder card with inline buttons |

---

## Build Phases

### Phase 1 — Infrastructure (Weeks 1–2)

**Objective:** Set up data layer and integrations.

- [ ] Provision Supabase PostgreSQL instance — enable pgvector extension
- [ ] Define schema: themes, companies, founders tables + junction tables
- [ ] Build Living Investment Memo read/write layer (CRUD in Python)
- [ ] Set up API integrations: arXiv, GitHub, USPTO, pytrends (all free; only GitHub needs a token)
- [ ] Set up Telegram bot via BotFather — configure inline keyboard callback handlers
- [ ] Implement Playwright scraper for YC company list and Tracxn snippets

**Success Criteria:** Can write a test theme to Supabase, retrieve it via pgvector semantic search, and send a test Telegram message with functional inline buttons.

---

### Phase 2 — Agent Development (Weeks 3–5)

**Objective:** Build and test each agent independently before integration.

#### Week 3: Horizon Scanner
- [ ] Implement arXiv paper fetcher (filter by category, citation velocity)
- [ ] Implement GitHub trending repo fetcher (stars/week growth rate)
- [ ] Implement USPTO patent fetcher (technology classification codes)
- [ ] Integrate pytrends for keyword acceleration curves
- [ ] Build embedding + clustering pipeline (text → vectors → HDBSCAN → theme labels)
- [ ] Build novelty scoring (compare theme embedding to existing themes via pgvector)
- [ ] Build `signal_maturity` classifier based on source mix
- [ ] Test: input 100 papers from Jan 2024 — verify it surfaces themes that became crowded by Jan 2025

#### Week 4: Market Cartographer
- [ ] Implement YC company list scraper (filtered by founding date, employee count)
- [ ] Implement OpenCorporates free tier search
- [ ] Implement SEC EDGAR comparable revenue fetcher
- [ ] Build TAM estimation logic with confidence flagging (`low` / `medium` / `high`)
- [ ] Build competitive segmentation (sort by stage, identify public comps)
- [ ] Test with 3 known themes: "AI coding assistants", "vertical SaaS healthcare", "climate fintech"

#### Week 5: Founder Radar + Orchestrator
- [ ] Implement Twitter/X monitoring (bio text changes, follower graph shifts)
- [ ] Implement GitHub monitoring (new repos, contribution patterns of tracked individuals)
- [ ] Implement Semantic Scholar researcher departure detection
- [ ] Implement cautious LinkedIn public-page scraper via Playwright
- [ ] Build signal scoring system with configurable weights
- [ ] Build Orchestrator: task routing, Living Investment Memo merge logic, escalation thresholds
- [ ] Build Telegram notification formatter + inline button callback handlers
- [ ] Wire all agents into orchestrator graph using LangGraph

**Success Criteria:** Manually trigger each agent, receive structured output, see it merged into Living Investment Memo, and receive Telegram card with working decision buttons.

---

### Phase 3 — Scheduling + Deployment (Week 6)

**Objective:** Automate end-to-end workflow and deploy.

- [ ] Set up Celery + Redis for task scheduling
- [ ] Configure daily cron for Horizon Scanner (06:00 UTC)
- [ ] Configure weekly cron for Founder Radar (Monday 08:00 UTC)
- [ ] Deploy via Docker Compose (single cloud instance)
- [ ] Run end-to-end integration test: seed 5 weak signals → verify full pipeline → receive Telegram card
- [ ] Run 7-day autonomous test — zero manual intervention required

**Success Criteria:** System runs autonomously for 7 days. At least one novel theme surfaced and mapped. At least one founder card delivered with functional decision buttons.

---

## Environment Variables

```bash
# LLM Provider
LLM_API_KEY=

# Supabase (PostgreSQL + pgvector — replaces Pinecone + Neo4j)
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_ANON_KEY=

# Free Data Sources
GITHUB_TOKEN=           # Free — needed for higher rate limits

# Notifications
TELEGRAM_BOT_TOKEN=     # From BotFather
TELEGRAM_CHAT_ID=       # Your personal or group chat ID

# Task Queue
REDIS_URL=redis://localhost:6379
```

> **Removed vs original spec:** `PINECONE_API_KEY`, `NEO4J_*`, `CRUNCHBASE_API_KEY`, `PROXYCURL_API_KEY`, `APIFY_TOKEN`, `SERPER_API_KEY`, `SLACK_BOT_TOKEN` — all eliminated. The only paid dependency is your LLM provider.

---

## Repository Structure

```
conviction-engine/
├── agents/
│   ├── orchestrator.py            # Central coordinator
│   ├── horizon_scanner.py         # Theme discovery from weak signals
│   ├── market_cartographer.py     # Competitive landscape mapping
│   └── founder_radar.py           # Founder signal tracking
│
├── db/
│   ├── supabase_client.py         # Connection + query helpers
│   ├── schema.sql                 # Table + pgvector definitions
│   └── living_memo.py             # Living Investment Memo CRUD
│
├── integrations/
│   ├── arxiv.py
│   ├── github.py
│   ├── uspto.py
│   ├── pytrends_client.py
│   ├── yc_scraper.py              # YC company list
│   ├── opencorporates.py
│   ├── edgar.py
│   └── linkedin_scraper.py        # Playwright, public pages only
│
├── notifications/
│   └── telegram.py                # Card formatting + inline button callbacks
│
├── scheduler/
│   ├── celery_app.py
│   └── tasks.py
│
├── tests/
│   ├── test_horizon_scanner.py
│   ├── test_market_cartographer.py
│   ├── test_founder_radar.py
│   └── test_orchestrator.py
│
├── docker-compose.yml
├── .env.example
├── requirements.txt
└── README.md
```

---

## Success Metrics

| Phase | Criteria |
|---|---|
| Phase 1 (Wks 1–6) | System runs autonomously 7 days with zero manual intervention. At least 2 novel themes surfaced. Knowledge graph: >50 companies, >20 founders, >5 themes. |
| Phase 2 (Mo 2–3) | Partner acts on at least 1 system-flagged theme. Founder Radar surfaces 3+ founders who subsequently announce fundraises. Active tracking of 5+ themes. |
| Phase 3 (Mo 4–6) | Knowledge graph reaches critical mass (>200 companies, >100 founders, >15 themes). System surfaces pattern matches against portfolio history. Partners report measurable time savings. |

---

## Future Extensions (Post-v1)

### Agent 4 — Deal Diligence Agent
Automates structured diligence when a pitch deck arrives: parses deck, scores team/market/product, flags anomalies, generates question list for partner meeting.

### Agent 5 — Portfolio Pulse Agent
Monitors portfolio companies via hiring velocity, news mentions, and GitHub activity — alerts partners to material changes.

### Agent 6 — LP Communications Agent
Auto-drafts quarterly LP letters and portfolio update memos using fund metrics and portfolio data.

### Infrastructure Upgrade Path
- Migrate from Supabase graph queries to Neo4j AuraDB when entity count exceeds ~500
- Add CRM sync (Affinity or Salesforce) for relationship tracking and sourcing attribution
- Build partner dashboard (Next.js) for visual knowledge graph exploration
- Add role-based access control for multi-fund configurations

---

## Technical Notes

### On LLM Selection
- **Long context window** (100k+ tokens) recommended for Orchestrator and Market Cartographer when synthesising large market maps
- **Strong tool use** capabilities needed across all agents
- **Cost optimisation:** use larger models for synthesis/reasoning; smaller models for classification tasks (e.g. "is this vaporware?")

### On Data Quality
The free-source stack produces lower fidelity company data than Crunchbase Pro. Mitigations:
- YC batches cover early-stage companies well — supplement with AngelList public pages
- OpenCorporates is best for geography and incorporation date, not sector classification
- Prioritise signal volume over individual data point precision — patterns emerge from aggregation

### On Scaling
v1 is designed for a single fund with 1–3 partners. For multi-fund firms: shard by fund focus, implement row-level security in Supabase, and configure different signal weights per fund strategy.

---

## Conclusion

The Conviction Engine represents a shift from reactive deal processing to proactive thesis generation. By continuously scanning weak signals, mapping emerging markets, and tracking high-potential founders, it compresses the time between market emergence and investment conviction — the core source of alpha in venture capital.

**Build order:** Start with Horizon Scanner → Market Cartographer → Founder Radar. Get that chain working end-to-end before adding complexity. The knowledge graph is the foundation — everything else compounds on top of it. The simplified infrastructure (Supabase only, no Pinecone or Neo4j) means the system is faster to stand up and cheaper to run while the graph seeds itself with real data.
