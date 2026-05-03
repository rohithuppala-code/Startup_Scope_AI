<div align="center">

# 🚀 StartupScope AI

### The Ultimate Idea Validation & Business Analytics Assistant

[![React](https://img.shields.io/badge/Next.js-14+-black?style=for-the-badge&logo=nextdotjs&logoColor=white)](https://nextjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Supabase](https://img.shields.io/badge/Supabase-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white)](https://supabase.com/)
[![Redis](https://img.shields.io/badge/Redis-DC382D?style=for-the-badge&logo=redis&logoColor=white)](https://redis.io/)
[![RabbitMQ](https://img.shields.io/badge/RabbitMQ-FF6600?style=for-the-badge&logo=rabbitmq&logoColor=white)](https://www.rabbitmq.com/)

*A cutting-edge, agentic AI platform that validates startup ideas using real-time market data, competitor intelligence, and multi-model consensus, guiding founders from raw concepts to market-ready strategies.*

[Features](#-features) • [Architecture](#-architecture) • [Data Flow Diagrams](#-data-flow-diagrams) • [API Reference](#-api-reference) • [Installation](#-installation) • [Tech Stack](#-tech-stack)

</div>

---

## ✨ Features

### 🧠 Advanced AI Validation Engine
- **Multi-Model Consensus:** Leverages Gemini (1.5 Pro / 2.5 Flash) for deep analysis and Groq (Llama 3.1 70B) for speed/fallback, merging outputs to provide balanced, bias-reduced evaluations.
- **Self-Healing Structured Output:** Built-in auto-correction loop that catches malformed AI outputs and re-prompts models with exact Pydantic schemas until validation succeeds.
- **Conversational RAG (Ask Your Report):** Uses native 768-dimensional Gemini `text-embedding-004` vectors stored in `pgvector` to semantically search and ground the AI's responses in real market data.
- **Three-Tier Redis Memory Storage:** Automatically deduplicates requests and injects historical insights from similar past ideas into the AI's context window.

### 🕵️ Real-Time Intelligence & Web Gathering
- **Advanced Firecrawl Pipeline:** An intelligent Search → Rank → Scrape → Extract cycle for deep competitor discovery.
- **Pricing & Funding Intelligence:** Automatically scrapes competitor pricing models and aggregates recent funding rounds.
- **Patent & IP Moat Scan:** Uses USPTO and EPO open APIs to check for potential patent conflicts or moats.
- **Job Posting Signal:** Analyzes competitor hiring trends as a proxy for their strategic direction.
- **Web Traffic Intelligence:** Extracts competitor traffic and engagement metrics to estimate market share.

### ⚡ Enterprise-Grade Infrastructure
- **Progressive Streaming:** Sections of the report (e.g., pricing, funding, patents) are pushed to the UI via WebSockets the *instant* they finish, rather than waiting for the entire pipeline.
- **Asynchronous Processing:** Robust background orchestration using RabbitMQ, Celery with Priority & Dead Letter Queues, and Distributed Redis Locks.
- **Cost Guard & Smart Alerts:** Pre-flight cost estimation, API charge reconciliation, and temporal drift tracking that triggers webhooks/alerts when your startup's market landscape changes significantly.

### 👥 Collaboration & Social
- **Team Workspaces:** Invite co-founders and advisors with role-based access control (Owner, Editor, Viewer).
- **Discord for Founders (Arena & Nexus):** A built-in social network to post validations, poll the community, and upvote/downvote ideas.
- **PDF Export:** Generate beautiful, dark-mode PDF pitch decks and reports from your validations using WeasyPrint.

---

## 🏗 Architecture

The system is split into a **Next.js Frontend** and a **FastAPI + Celery Backend**, backed by **Supabase (PostgreSQL)**, **Redis**, and **RabbitMQ**.

### High-Level Architecture Diagram

```mermaid
flowchart TB
    subgraph ClientLayer["🖥️ Frontend (Next.js + Tailwind)"]
        UI["React Components"]
        Store["Zustand Stores"]
        WS["WebSocket Client"]
    end

    subgraph BackendLayer["⚙️ Backend (FastAPI + Celery)"]
        API["FastAPI Endpoints"]
        WS_Manager["WebSocket Manager"]
        Worker["Celery Worker Nodes"]
        AI["AI Pipeline (Gemini + Groq)"]
    end

    subgraph InfraLayer["☁️ Infrastructure & State"]
        MQ[("RabbitMQ + DLQ")]
        Cache[("Redis: Cache, Locks, Pub/Sub")]
        DB[("Supabase PostgreSQL + pgvector")]
    end

    subgraph ExternalLayer["🌐 External APIs"]
        Firecrawl["Firecrawl API"]
        Traffic["Traffic APIs"]
        Patents["USPTO / EPO"]
        Webhooks["Outbound Webhooks"]
    end

    UI -->|REST| API
    WS <-->|WebSockets| WS_Manager
    
    API -->|Anchors State| DB
    API -->|Enqueues Task| MQ
    
    MQ -->|Consumes| Worker
    Worker -->|Scrapes| Firecrawl
    Worker -->|Queries| Traffic
    Worker -->|Queries| Patents
    Worker -->|Reasons & Self-Heals| AI
    Worker -->|Write-Through| DB
    Worker -->|Progressive Stream Events| Cache
    Worker -->|Fires| Webhooks
    
    Cache -->|Subscribes| WS_Manager
```

---

## 📊 Data Flow Diagrams

### Level 0 DFD (Context Diagram)

```mermaid
flowchart TB
    subgraph External["External Entities"]
        Founder("👤 Founder / User")
        Web("🌐 Competitor Web Pages")
        LLMs("🧠 External LLMs (Gemini, Groq)")
    end

    subgraph System["StartupScope AI System"]
        Core("Core System<br/>• Multi-Model Validation<br/>• Progressive Streaming<br/>• Cost Guard<br/>• Temporal Memory")
    end

    Founder -->|Submits Startup Idea| Core
    Founder -->|Follow-up Questions| Core
    
    Core -->|Progressive WS Streams| Founder
    Core -->|Final Validations & Webhooks| Founder

    Core -->|Search Intents & Scraping| Web
    Web -->|Raw HTML / Pricing / Traffic| Core
    
    Core -->|Prompts + Context Data| LLMs
    LLMs -->|Structured JSON / Corrected JSON| Core

    style Core fill:#8B5CF6,stroke:#EC4899,stroke-width:3px,color:#fff
```

### Level 1 DFD

```mermaid
flowchart TB
    subgraph Users["👥 Users"]
        Founder[("Founder")]
    end

    subgraph Orchestration["1.0 Orchestration & State"]
        API_Gateway["1.1 FastAPI Gateway"]
        Task_Queue["1.2 RabbitMQ Dispatch"]
        CostGuard["1.3 Cost Guard & Limits"]
    end

    subgraph Intelligence["2.0 Intelligence Gathering"]
        Scraper["2.1 Firecrawl Pipeline"]
        TrafficEngine["2.2 Web Traffic Insights"]
        IPEngine["2.3 Patent/IP Scan"]
        DataPipelines["2.4 Pricing & Funding"]
    end

    subgraph Analysis["3.0 Generative Analysis"]
        Consensus["3.1 Gemini + Groq Consensus"]
        SelfHeal["3.2 Self-Healing JSON Loop"]
        RAG["3.3 Vector Context (pgvector)"]
        Temporal["3.4 Temporal Versioning"]
    end

    subgraph DataStore["💾 Data Stores"]
        D1[("D1: Validations & Reports")]
        D2[("D2: RAG Embeddings (768-dim)")]
        D3[("D3: Redis Semantic Memory")]
    end

    Founder -->|Raw Idea| API_Gateway
    API_Gateway -->|Pre-flight Check| CostGuard
    API_Gateway -->|Task Payload| Task_Queue
    
    Task_Queue -->|Trigger| Scraper
    Task_Queue -->|Trigger| DataPipelines
    Task_Queue -->|Trigger| TrafficEngine
    Task_Queue -->|Trigger| IPEngine
    
    Scraper -->|Market Data| Consensus
    Consensus <-->|Fix Malformed JSON| SelfHeal
    
    Consensus -->|Final Report| D1
    Consensus -->|Embeddings| D2
    Consensus -->|Deduplication & Insights| D3
    Temporal -->|Drift Alerts| D1
    
    Founder -->|Chat Query| RAG
    D2 -->|Context Docs| RAG
    RAG -->|Answers| Founder

    style Orchestration fill:#F59E0B,stroke:#D97706,stroke-width:2px,color:#fff
    style Intelligence fill:#10B981,stroke:#059669,stroke-width:2px,color:#fff
    style Analysis fill:#8B5CF6,stroke:#7C3AED,stroke-width:2px,color:#fff
```

---

## 🧩 Sequence & Class Diagrams

### Core Validation Sequence Diagram

```mermaid
sequenceDiagram
    participant C as Client
    participant API as FastAPI
    participant DB as Supabase
    participant MQ as RabbitMQ
    participant W as Celery Worker
    participant R as Redis PubSub
    participant AI as Gemini and Groq

    C->>API: POST /api/v1/validate (Idea)
    API->>DB: Insert validation (Status: pending)
    API->>MQ: send_task('process_validation')
    API-->>C: 202 Accepted
    
    C->>API: WS Connect (/ws/validation/{id})
    API->>R: Subscribe to channel
    
    MQ-->>W: Consume task
    W->>R: Lock & Deduplicate Check
    
    W->>W: Firecrawl Scrape & RAG Embed
    W->>AI: Generate Report (Gemini + Groq)
    AI-->>W: Structured JSON output (with self-healing)
    
    W->>R: Publish Event (Consensus section ready)
    R-->>API: Receive Event
    API-->>C: WS Push (Partial Consensus UI Render)
    
    par Parallel Data Pipelines
        W->>W: Run Pricing Pipeline
        W->>R: Publish Event (Pricing ready)
        R-->>API: WS Push
        W->>W: Run Patent Pipeline
        W->>R: Publish Event (Patents ready)
        R-->>API: WS Push
    end
    
    W->>DB: Update row (Status: completed, JSON payload)
    W->>R: Publish Event (Final completed state)
    R-->>API: Receive Event
    API-->>C: WS Push (Pipeline fully completed)
```

### Entity Relationship (Class) Diagram

```mermaid
erDiagram
    PROFILES ||--o{ VALIDATIONS : creates
    PROFILES ||--o{ WORKSPACE_MEMBERS : belongs_to
    WORKSPACES ||--o{ WORKSPACE_MEMBERS : contains
    VALIDATIONS ||--o{ RAG_CHUNKS : generates
    VALIDATIONS ||--o{ PRICING_INTELLIGENCE : has
    VALIDATIONS ||--o{ WEB_TRAFFIC : has
    VALIDATIONS ||--o{ FUNDING_INTELLIGENCE : has
    
    POSTS ||--o{ COMMENTS : has
    POSTS ||--o{ POLLS : includes
    PROFILES ||--o{ POSTS : authors

    PROFILES {
        uuid id PK
        text username
        text full_name
        integer karma_score
        text bio
    }

    VALIDATIONS {
        uuid id PK
        uuid user_id FK
        text idea_description
        validation_status status
        jsonb report_json
        float consensus_confidence
        vector idea_embedding
        timestamp created_at
    }

    WORKSPACES {
        uuid id PK
        text name
        uuid created_by FK
    }

    WORKSPACE_MEMBERS {
        uuid id PK
        uuid workspace_id FK
        uuid user_id FK
        text role
    }

    RAG_CHUNKS {
        uuid id PK
        uuid validation_id FK
        text chunk_text
        vector embedding
    }

    POSTS {
        uuid id PK
        uuid user_id FK
        uuid validation_id FK
        text title
        text content
        integer upvote_count
    }
```

---

## 📡 API Reference

### Validation Engine
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/validate` | Submits a new idea for background AI processing. |
| `GET`  | `/api/v1/validate/{id}` | Fetches the completed validation report (Cache-Aside). |
| `WS`   | `/ws/validation/{id}` | Real-time progressive WebSocket stream for pipeline milestones. |
| `POST` | `/api/v1/validate/{id}/summarize` | Generates an AI summary of a completed report. |

### RAG & AI Chat
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/chat/{validation_id}` | Ask follow-up questions grounded in the report data. |
| `POST` | `/api/v1/compare` | Compare multiple startup ideas using a VC-like matrix. |

### Collaboration & Export
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/workspaces` | Create a new shared workspace. |
| `POST` | `/api/v1/workspaces/{id}/invite` | Invite users via email to collaborate. |
| `GET`  | `/api/v1/export/{id}/pdf` | Generates and returns a signed URL for a PDF pitch deck. |

---

## 🛠 Tech Stack

### Frontend
- **Framework:** Next.js 14+ (App Router)
- **Styling:** Tailwind CSS + Framer Motion
- **State Management:** Zustand
- **Auth:** Supabase Auth Helpers

### Backend
- **Framework:** FastAPI (Python 3.10+)
- **Task Queue:** Celery + RabbitMQ (with Dead Letter Queues)
- **Cache & Pub/Sub:** Redis
- **Database:** Supabase (PostgreSQL) + pgvector
- **AI/LLMs:** Google Gemini (1.5-Pro / 2.5-Flash), Groq (Llama 3.1 70B), Gemini `text-embedding-004`
- **Resilience:** Tenacity (for self-healing AI outputs)
- **Web Scraping:** Firecrawl

---

## 🚀 Installation & Local Setup

### 1. Prerequisites
- Docker & Docker Compose
- Python 3.10+
- Node.js 18+
- Supabase Account (or local Supabase stack)

### 2. Infrastructure Setup (Redis & RabbitMQ)
We use Docker to spin up the message broker and cache layer.

```bash
cd backend
docker compose up -d
```

### 3. Backend Setup
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate
pip install -r requirements.txt

# Create .env and fill in API keys
cp .env.example .env

# Run FastAPI Server
uvicorn app.main:app --reload --port 8000

# In a separate terminal, run the Celery Worker
celery -A app.worker.celery_tasks worker --loglevel=info
```
*(Alternatively, use `./startup.sh` if running on Unix to boot everything at once).*

### 4. Frontend Setup
```bash
cd frontend
npm install

# Create .env.local and add Supabase URL and Anon Key
cp .env.example .env.local

npm run dev
```
The application will be available at `http://localhost:3000`.

---

## 📄 License

This project is proprietary. All rights reserved. Built for the founders of tomorrow.

<div align="center">
<b>Validate Faster. Pivot Smarter. Build Better.</b>
</div>