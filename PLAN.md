# Conviction Engine v3 — Hive-Mind Implementation Plan

> Personal-first agent system for VC/Growth Equity (Series B+), scalable to fund-wide deployment.

---

## Vision

A **hive-mind agent architecture** where a single Central Agent holds all institutional knowledge (themes, founders, market maps, deal history) and spawns **personal Sub-Agents** — one per team member — each with its own memory, personality, and workflow preferences. Sub-Agents query the Central Agent on a need-basis, and feed learnings back into the shared knowledge graph.

**Phase 1 (this plan):** Build a fully functional system for a single user (you). The Central Agent and your personal Sub-Agent will initially run as a tightly coupled pair. The architecture is designed so that adding a second user later means spawning a new Sub-Agent — not rebuilding the system.

```
                    ┌─────────────────────────────┐
                    │       CENTRAL AGENT          │
                    │  (Institutional Knowledge)   │
                    │                              │
                    │  - Knowledge Graph           │
                    │  - Living Investment Memo    │
                    │  - Theme / Founder / Market  │
                    │    canonical records         │
                    │  - Cross-user deduplication  │
                    └──────────┬──────────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
     ┌────────▼──────┐  ┌─────▼────────┐  ┌───▼──────────┐
     │  YOUR SUB-    │  │  (Future)    │  │  (Future)    │
     │  AGENT        │  │  Partner B   │  │  Analyst C   │
     │               │  │  Sub-Agent   │  │  Sub-Agent   │
     │ - Your prefs  │  │              │  │              │
     │ - Your focus  │  │              │  │              │
     │   sectors     │  │              │  │              │
     │ - Your comms  │  │              │  │              │
     │   style       │  │              │  │              │
     └───────────────┘  └──────────────┘  └──────────────┘
```

---

## Why Hive-Mind > Monolithic Agent

| Monolithic (v2) | Hive-Mind (v3) |
|---|---|
| One system, one user, one set of preferences | Shared knowledge, personalised interfaces |
| Adding users = forking the system | Adding users = spawning a Sub-Agent |
| All alerts go to everyone | Each Sub-Agent filters by user's focus areas, deal stage preferences, and communication cadence |
| No institutional memory separation | Central Agent = firm-level memory; Sub-Agent = personal memory (your notes, your conviction calls, your relationship context) |

---

## Architecture

### Layer 1: Central Agent (The Queen)

The Central Agent is the **single source of truth**. It owns the knowledge graph, runs the data-gathering worker agents (Horizon Scanner, Market Cartographer, Founder Radar from SPEC.md), and exposes a structured API for Sub-Agents to query.

**Responsibilities:**
- Run all data ingestion pipelines (arXiv, GitHub, USPTO, pytrends, YC, EDGAR, etc.)
- Maintain the canonical knowledge graph (themes, companies, founders, relationships)
- Maintain the Living Investment Memo (firm-level view)
- Deduplicate entities across Sub-Agent contributions
- Respond to Sub-Agent queries ("What do we know about Theme X?", "Who are the top founders in space Y?")
- Accept Sub-Agent write-backs ("I met this founder, here's my notes", "Mark this theme as pass for me")

**Worker Agents (unchanged from SPEC.md, owned by Central Agent):**

| Worker | Schedule | Role |
|---|---|---|
| Horizon Scanner | Daily 06:00 UTC | Scan for emerging themes via arXiv, GitHub, USPTO, pytrends |
| Market Cartographer | On-demand | Build market maps when novel themes are confirmed |
| Founder Radar | Weekly + on-demand | Track high-signal founders before they announce |

These workers feed the Central Agent's knowledge graph. Sub-Agents never call data sources directly — they always go through the Central Agent.

### Layer 2: Sub-Agent (The Worker Bee)

Each Sub-Agent is a **personalised interface** to the Central Agent. For Phase 1, there is only one: yours.

**Responsibilities:**
- Maintain a personal memory store (your notes, your conviction scores, your relationship history)
- Filter Central Agent outputs by your preferences (sectors, deal stages, geographies, signal thresholds)
- Deliver notifications tuned to your cadence and format preferences
- Accept your inputs (voice notes, meeting notes, ad-hoc queries) and either store locally or write back to Central Agent
- Generate personalised briefings (daily digest, weekly memo, pre-meeting prep)
- Draft outreach in your communication style

**Personal Memory (Sub-Agent-only data):**

```json
{
  "user_id": "you",
  "focus_sectors": ["AI infrastructure", "developer tools", "fintech"],
  "deal_stage_preference": "series_b_plus",
  "geography_preference": ["US", "Europe"],
  "alert_threshold": {
    "theme_novelty_min": 0.75,
    "founder_signal_min": 45
  },
  "communication_style": "concise, data-driven, no fluff",
  "notification_cadence": "real_time_for_high_signal, daily_digest_for_rest",
  "relationships": [
    {
      "founder_id": "uuid",
      "last_contact": "2026-03-10",
      "notes": "Met at conference. Strong technical founder. Follow up in 2 weeks.",
      "personal_conviction": "high"
    }
  ],
  "thesis_overrides": [
    {
      "theme_id": "uuid",
      "your_conviction": "high",
      "your_notes": "This is underappreciated. The EDGAR comps show 3x growth.",
      "central_agent_status": "emerging"
    }
  ]
}
```

### Layer 3: Communication Protocol (The Waggle Dance)

Sub-Agents and the Central Agent communicate through a structured message protocol:

```python
# Sub-Agent → Central Agent queries
class HiveQuery:
    query_type: str          # "theme_lookup", "founder_search", "market_map", "full_brief"
    parameters: dict         # Filters, search terms, theme IDs
    requesting_user: str     # Sub-Agent identity
    urgency: str             # "real_time", "batch", "background"

# Central Agent → Sub-Agent responses
class HiveResponse:
    data: dict               # Structured response data
    freshness: datetime      # When this data was last updated
    confidence: str          # "high", "medium", "low"
    related_entities: list   # Cross-references for the Sub-Agent to explore

# Sub-Agent → Central Agent write-backs
class HiveWriteBack:
    entity_type: str         # "founder_note", "thesis_conviction", "meeting_log"
    entity_id: str           # UUID of the entity being annotated
    user_id: str             # Who is writing
    payload: dict            # The data to store
    visibility: str          # "personal" (Sub-Agent only) or "shared" (Central Agent)
```

---

## Implementation Plan

### Phase 1: Foundation (Weeks 1-2)

**Goal:** Central Agent data layer + knowledge graph operational.

#### Week 1: Infrastructure
- [ ] Provision Supabase PostgreSQL — enable pgvector extension
- [ ] Deploy schema from SPEC.md (themes, companies, founders, junction tables)
- [ ] Add Sub-Agent tables:

```sql
-- Sub-Agent personal memory
CREATE TABLE user_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT UNIQUE NOT NULL,
    focus_sectors TEXT[],
    deal_stage_preference TEXT,
    geography_preference TEXT[],
    alert_thresholds JSONB,
    communication_style TEXT,
    notification_cadence TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE user_entity_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL REFERENCES user_profiles(user_id),
    entity_type TEXT NOT NULL,  -- 'theme', 'founder', 'company'
    entity_id UUID NOT NULL,
    personal_conviction TEXT,   -- 'high', 'medium', 'low', 'pass'
    notes TEXT,
    last_contact TIMESTAMPTZ,
    visibility TEXT DEFAULT 'personal',  -- 'personal' or 'shared'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE user_interaction_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    interaction_type TEXT,      -- 'query', 'write_back', 'decision', 'meeting_note'
    payload JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

- [ ] Build Living Investment Memo CRUD layer (Python)
- [ ] Set up Telegram bot (BotFather) with inline keyboard callbacks
- [ ] Set up API clients: arXiv, GitHub, USPTO, pytrends (all free)
- [ ] Set up Playwright scrapers for YC company list and Tracxn snippets

#### Week 2: Central Agent Core
- [ ] Build the Central Agent as a LangGraph stateful agent
- [ ] Implement HiveQuery / HiveResponse / HiveWriteBack message protocol
- [ ] Build the query router: parse Sub-Agent queries → dispatch to knowledge graph or trigger worker agents
- [ ] Build entity deduplication logic (fuzzy match on company names, founder names)
- [ ] Test: write a theme, query it back, write a note against it, retrieve note

**Exit Criteria:** Can programmatically write entities to the knowledge graph, query them semantically via pgvector, and round-trip a HiveQuery/HiveResponse.

---

### Phase 2: Worker Agents (Weeks 3-5)

**Goal:** All three worker agents operational, feeding the Central Agent.

These are built exactly as specified in SPEC.md but wired to write through the Central Agent rather than directly to the database.

#### Week 3: Horizon Scanner
- [ ] arXiv paper fetcher (cs.AI, cs.RO, q-bio, eess; citation velocity filter)
- [ ] GitHub trending repo fetcher (>200 stars/week from base <1,000)
- [ ] USPTO patent fetcher (technology classification codes)
- [ ] pytrends keyword acceleration curves
- [ ] Embedding + HDBSCAN clustering pipeline
- [ ] Novelty scoring via pgvector cosine similarity against existing themes
- [ ] Signal maturity classifier (pre_commercial → early_commercial → accelerating → crowded)
- [ ] Wire to Central Agent: scanner outputs → Central Agent → knowledge graph
- [ ] Backtest: feed 100 arXiv papers from Jan 2024 → verify themes that became crowded by Jan 2025 are surfaced

#### Week 4: Market Cartographer
- [ ] YC company list scraper (filtered by founding date, sector)
- [ ] OpenCorporates free tier search
- [ ] SEC EDGAR comparable revenue fetcher
- [ ] Bottom-up TAM estimation with confidence flags (low/medium/high)
- [ ] Competitive segmentation (early-stage / growth-stage / incumbents)
- [ ] Wire to Central Agent: cartographer outputs → Central Agent → knowledge graph
- [ ] Test with known themes: "AI coding assistants", "vertical SaaS healthcare", "climate fintech"

#### Week 5: Founder Radar
- [ ] Twitter/X bio change monitoring + follower graph analysis
- [ ] GitHub new repo creation + contribution spike detection
- [ ] Semantic Scholar researcher departure detection
- [ ] LinkedIn public-page Playwright scraper (cautious, public only)
- [ ] Signal scoring system (configurable weights from SPEC.md)
- [ ] Wire to Central Agent: founder profiles → Central Agent → knowledge graph
- [ ] Test: seed 10 known founders → verify signal scores align with expectations

**Exit Criteria:** Each worker agent can be triggered independently. Outputs are stored in the Central Agent's knowledge graph. Cross-references between themes, companies, and founders are populated.

---

### Phase 3: Your Sub-Agent (Week 6)

**Goal:** Your personalised Sub-Agent is operational — the interface you interact with daily.

- [ ] Build Sub-Agent as a LangGraph agent with your user profile loaded
- [ ] Implement personal memory store (user_entity_notes, user_interaction_log)
- [ ] Build preference-based filtering:
  - Filter themes by your focus sectors and deal stage preference
  - Filter founders by your geography preference and signal threshold
  - Apply your alert thresholds (theme novelty > 0.75, founder signal > 45)
- [ ] Build notification pipeline:
  - Real-time Telegram alerts for high-signal items
  - Daily digest (morning briefing) with everything below threshold
  - Weekly synthesis memo (themes evolved, new founders, market moves)
- [ ] Build input handlers:
  - Accept meeting notes (text) → parse → store as user_entity_notes
  - Accept ad-hoc queries ("What do we know about company X?") → HiveQuery to Central Agent → format response
  - Accept conviction updates ("I'm high conviction on theme Y") → write-back to personal memory + optionally share to Central Agent
- [ ] Build draft outreach generator:
  - Pull founder profile from Central Agent
  - Pull your relationship history from personal memory
  - Generate outreach in your communication style
- [ ] Build pre-meeting briefing generator:
  - Input: company name or founder name
  - Output: everything the system knows (theme context, market map, founder signals, your prior notes)

**Exit Criteria:** You can interact with your Sub-Agent via Telegram. It filters Central Agent outputs to your preferences, stores your notes, and generates personalised briefings.

---

### Phase 4: Scheduling + Deployment (Week 7)

**Goal:** Fully autonomous daily/weekly operation.

- [ ] Set up Celery + Redis for task scheduling
- [ ] Daily cron: Horizon Scanner (06:00 UTC) → Central Agent processing → Sub-Agent notification filtering → your Telegram
- [ ] Weekly cron: Founder Radar (Monday 08:00 UTC) → same pipeline
- [ ] Weekly cron: Sub-Agent weekly synthesis memo (Friday 17:00 UTC)
- [ ] Deploy via Docker Compose on single cloud instance:

```yaml
services:
  central-agent:
    build: ./central_agent
    env_file: .env
    depends_on: [redis, supabase]

  sub-agent-you:
    build: ./sub_agent
    env_file: .env
    environment:
      - USER_ID=you
      - USER_PROFILE_PATH=/config/your_profile.json
    depends_on: [central-agent]

  redis:
    image: redis:7-alpine

  celery-worker:
    build: ./scheduler
    command: celery -A tasks worker --loglevel=info
    depends_on: [redis, central-agent]

  celery-beat:
    build: ./scheduler
    command: celery -A tasks beat --loglevel=info
    depends_on: [redis]
```

- [ ] End-to-end integration test: seed 5 weak signals → verify full pipeline → receive personalised Telegram notification
- [ ] Run 7-day autonomous test

**Exit Criteria:** System runs autonomously for 7 days. You receive filtered, personalised alerts. Your notes and decisions persist across sessions.

---

## Scaling to Team (Future Phase 5)

When you're ready to onboard another team member, the process is:

1. **Create their user profile** in `user_profiles` table (sectors, preferences, thresholds)
2. **Spawn a new Sub-Agent container** with their `USER_ID` and profile config
3. **Set up their Telegram bot** (or share the existing bot with per-user chat routing)
4. **No changes to Central Agent or workers** — they already serve multiple Sub-Agents

```yaml
# Add to docker-compose.yml
  sub-agent-partner-b:
    build: ./sub_agent
    env_file: .env
    environment:
      - USER_ID=partner_b
      - USER_PROFILE_PATH=/config/partner_b_profile.json
    depends_on: [central-agent]
```

### Multi-User Features (unlocked at scale)
- **Cross-pollination:** Central Agent detects when two Sub-Agents are independently tracking the same theme/founder → alerts both
- **Coverage gaps:** Central Agent identifies themes no Sub-Agent is watching → flags to team lead
- **Relationship deconfliction:** Prevents two partners from reaching out to the same founder independently
- **Collective conviction scoring:** Aggregate individual conviction scores into a firm-level view
- **Shared annotations:** Sub-Agents can mark notes as `visibility: "shared"` to contribute to institutional knowledge

---

## Repository Structure

```
conviction-engine/
├── central_agent/
│   ├── agent.py                     # Central Agent LangGraph definition
│   ├── query_router.py              # Routes HiveQueries to knowledge graph or workers
│   ├── deduplication.py             # Entity deduplication (fuzzy matching)
│   └── workers/
│       ├── horizon_scanner.py       # Theme discovery
│       ├── market_cartographer.py   # Market mapping
│       └── founder_radar.py         # Founder tracking
│
├── sub_agent/
│   ├── agent.py                     # Sub-Agent LangGraph definition
│   ├── personal_memory.py           # User-specific memory CRUD
│   ├── preference_filter.py         # Filter Central Agent outputs by user prefs
│   ├── briefing_generator.py        # Daily digest, weekly memo, pre-meeting briefs
│   ├── outreach_drafter.py          # Personalised outreach generation
│   └── input_handlers.py           # Meeting notes, ad-hoc queries, conviction updates
│
├── protocol/
│   ├── messages.py                  # HiveQuery, HiveResponse, HiveWriteBack definitions
│   └── serialization.py            # Message serialization/deserialization
│
├── db/
│   ├── supabase_client.py           # Connection + query helpers
│   ├── schema.sql                   # All table definitions (central + sub-agent)
│   └── living_memo.py               # Living Investment Memo CRUD
│
├── integrations/
│   ├── arxiv.py
│   ├── github.py
│   ├── uspto.py
│   ├── pytrends_client.py
│   ├── yc_scraper.py
│   ├── opencorporates.py
│   ├── edgar.py
│   └── linkedin_scraper.py
│
├── notifications/
│   ├── telegram.py                  # Card formatting + inline callbacks
│   └── digest.py                    # Daily/weekly digest formatting
│
├── scheduler/
│   ├── celery_app.py
│   └── tasks.py
│
├── config/
│   ├── your_profile.json            # Your Sub-Agent preferences
│   └── profile_template.json        # Template for new team members
│
├── tests/
│   ├── test_central_agent.py
│   ├── test_sub_agent.py
│   ├── test_protocol.py
│   ├── test_horizon_scanner.py
│   ├── test_market_cartographer.py
│   └── test_founder_radar.py
│
├── docker-compose.yml
├── .env.example
├── requirements.txt
├── SPEC.md                          # Original technical specification
└── PLAN.md                          # This file
```

---

## Environment Variables

```bash
# LLM Provider
LLM_API_KEY=

# Supabase (PostgreSQL + pgvector)
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_ANON_KEY=

# Free Data Sources
GITHUB_TOKEN=           # Free — needed for higher rate limits

# Notifications
TELEGRAM_BOT_TOKEN=     # From BotFather
TELEGRAM_CHAT_ID=       # Your personal chat ID

# Task Queue
REDIS_URL=redis://localhost:6379

# Sub-Agent Config
USER_ID=you
USER_PROFILE_PATH=/config/your_profile.json
```

---

## Key Differences from SPEC.md (v2)

| Aspect | v2 (SPEC.md) | v3 (This Plan) |
|---|---|---|
| Architecture | Monolithic orchestrator + 3 workers | Central Agent (queen) + Sub-Agents (workers) |
| User model | Single user assumed | Personal-first, multi-user ready |
| Memory | Single knowledge graph | Shared knowledge graph + per-user personal memory |
| Notifications | Same alerts for everyone | Preference-filtered, personalised per Sub-Agent |
| Inputs | Telegram button taps only | Meeting notes, ad-hoc queries, conviction updates, outreach drafts |
| Outputs | Theme/founder cards | Cards + daily digests + weekly memos + pre-meeting briefs |
| Scaling | Requires rebuild | Spawn a new Sub-Agent container + user profile |
| Communication | Direct function calls | Structured HiveQuery/HiveResponse protocol |

---

## Build Order Summary

```
Week 1-2: Infrastructure + Central Agent core
Week 3-5: Worker agents (Horizon Scanner → Market Cartographer → Founder Radar)
Week 6:   Your Sub-Agent (personalisation layer)
Week 7:   Scheduling + deployment + 7-day autonomous test
```

Start with the Central Agent's knowledge graph and the Horizon Scanner. Get one theme flowing end-to-end — from arXiv paper to your Telegram — before building breadth. The hive-mind protocol is the architectural bet: get it right early, and scaling to your team is just configuration.
