# ICT Agent - Complete Project Knowledge Base

> **Purpose:** This document serves as a comprehensive knowledge transfer for LLMs working on this codebase. It contains everything needed to understand, modify, and extend the ICT Agent system.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Directory Structure](#2-directory-structure)
3. [Business Context & Use Case](#3-business-context--use-case)
4. [Core Architecture](#4-core-architecture)
5. [Core Modules Deep Dive](#5-core-modules-deep-dive)
6. [Tools System](#6-tools-system)
7. [Configuration Files](#7-configuration-files)
8. [Data Models & Schemas](#8-data-models--schemas)
9. [API Reference](#9-api-reference)
10. [External Integrations](#10-external-integrations)
11. [Execution Flow](#11-execution-flow)
12. [Deployment & Infrastructure](#12-deployment--infrastructure)
13. [Design Patterns & Optimizations](#13-design-patterns--optimizations)
14. [Lead Pipeline & Stages](#14-lead-pipeline--stages)
15. [Message Templates System](#15-message-templates-system)
16. [Critical Rules & Constraints](#16-critical-rules--constraints)
17. [Troubleshooting Guide](#17-troubleshooting-guide)
18. [Quick Reference](#18-quick-reference)

---

## 1. Project Overview

### Identity
- **Project Name:** ICT Agent - Intelligent Chat Agent with Long-Term Memory
- **Version:** 0.1.0
- **Language:** Python 3.13+
- **Type:** FastAPI REST API + LangGraph Agent
- **Repository:** Local development with GitHub CI/CD

### Tech Stack
| Layer | Technology |
|-------|------------|
| API Framework | FastAPI with Uvicorn |
| Agent Framework | LangGraph + LangChain |
| LLM | OpenAI GPT (gpt-4.1-mini, 128k context) |
| Embeddings | OpenAI text-embedding-3-small (512 dims) |
| Vector Database | ChromaDB |
| Cache | Redis (optional) + In-memory fallback |
| Google Integration | Sheets API v4 + OAuth2/Service Account |
| Containerization | Docker with multi-stage builds |
| Reverse Proxy | Nginx |
| CI/CD | GitHub Actions → Docker Hub → Hostinger |

### Purpose Statement
Production-ready AI chatbot for course enrollment at Institute of Corporate & Taxation (ICT). The agent acts as "Tanveer Awan", an enrollment advisor, guiding leads through the enrollment funnel via WhatsApp communication.

---

## 2. Directory Structure

```
ict_agent/
├── app.py                          # FastAPI main application (915 lines)
│                                   # Entry point, API endpoints, middleware
│
├── core/                           # Core business logic
│   ├── __init__.py
│   ├── agent.py                   # LangGraph agent (659 lines)
│   │                              # Main conversation engine
│   ├── memory.py                  # Long-term memory system (628 lines)
│   │                              # ChromaDB + JSON metadata
│   ├── sheets_cache.py            # Google Sheets caching (687 lines)
│   │                              # Real-time sync + Redis cache
│   ├── context_injector.py        # Stage-based context injection
│   │                              # Proactive data loading
│   └── background_tasks.py        # Async polling tasks
│                                   # Fallback sheet sync
│
├── tools/                          # LangChain tool integrations
│   ├── __init__.py
│   ├── sheets_tools.py            # Google Sheets data fetching (5 tools)
│   ├── mcp_rag_tools.py           # Lead data capture tool
│   └── template_tools.py          # Message template retrieval
│
├── config/                         # Configuration files
│   ├── prompt.txt                 # System prompt (772+ lines)
│   │                              # Agent identity, rules, flow
│   └── templates.json             # Message templates (~1500 lines)
│                                   # 40+ pre-defined responses
│
├── docker/                         # Docker configuration
│   ├── Dockerfile                 # Multi-stage production build
│   └── entrypoint.sh             # Container entry script
│
├── scripts/                        # Utility scripts
│   ├── run_api.py                # API server runner
│   └── setup_oauth2.py           # OAuth2 setup helper
│
├── nginx/                         # Nginx reverse proxy config
│
├── docs/                          # Documentation
│   ├── DOCKER_PRODUCTION.md
│   ├── GOOGLE_SHEETS_CACHING_IMPLEMENTATION.md
│   ├── GOOGLE_SHEETS_WEBHOOK_SETUP.md
│   ├── NGINX_SETUP.md
│   ├── PRODUCTION_OPTIMIZATIONS.md
│   ├── SETUP_COMPLETE_GUIDE.md
│   └── SETUP_OAUTH2.md
│
├── pyproject.toml                 # Dependencies (Python >=3.13)
├── uv.lock                        # Lock file (UV package manager)
├── docker-compose.yml             # Development compose
├── docker-compose.prod.yml        # Production compose
├── .env.example                   # Environment template (186 lines)
├── README.md                      # Main documentation
└── .github/workflows/deploy.yml   # CI/CD pipeline
```

---

## 3. Business Context & Use Case

### Organization
- **Client:** Institute of Corporate & Taxation (ICT)
- **Location:** Pakistan
- **Industry:** Professional Training & Education
- **Courses Offered:** 12+ courses in taxation, compliance, import/export, stock trading

### Target Users
1. **Course Enrollment Leads** - Potential students on WhatsApp
2. **ICT Enrollment Team** - Internal staff via API
3. **Integration Partners** - External systems via REST API

### Agent Persona
- **Name:** Tanveer Awan
- **Role:** Enrollment Advisor
- **Gender:** Male
- **Communication Style:** Professional, helpful, bilingual (English + Roman Urdu)

### Available Courses
1. CTA - Chartered Tax Advisor
2. ATO - Advance Taxation & Compliance Officer
3. CCP - Certified Compliance Professional
4. ACMA - Associate Cost & Management Accountant
5. CFP - Certified Financial Planner
6. CIEP - Certified Import & Export Professional
7. TEXP - Tax Expert Program
8. AIFM - AI & Finance Management
9. ATA - Advanced Tax Advisor
10. PSX - Pakistan Stock Exchange Trading
11. QuickBooks - Accounting Software Training
12. And more...

---

## 4. Core Architecture

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                           CLIENT (WhatsApp)                          │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      NGINX REVERSE PROXY                            │
│                   (SSL, Load Balancing, Compression)                 │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      FASTAPI APPLICATION (app.py)                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │
│  │ API Endpoints │  │  Middleware  │  │ Health Check │               │
│  │  POST /chat   │  │ CORS, Auth   │  │ GET /health  │               │
│  └──────────────┘  └──────────────┘  └──────────────┘               │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   LANGGRAPH AGENT (core/agent.py)                    │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │                    StateGraph Workflow                          │ │
│  │  ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐        │ │
│  │  │retrieve │ → │  agent  │ → │  tools  │ → │summarize│ → END  │ │
│  │  │_context │   │  (LLM)  │   │(optional)│   │         │        │ │
│  │  └─────────┘   └─────────┘   └─────────┘   └─────────┘        │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
         │                    │                      │
         ▼                    ▼                      ▼
┌─────────────────┐  ┌─────────────────┐   ┌─────────────────────────┐
│  LONG-TERM      │  │   OPENAI API    │   │    TOOLS                │
│  MEMORY         │  │                 │   │  ┌──────────────────┐   │
│  ┌───────────┐  │  │  ┌───────────┐  │   │  │ sheets_tools     │   │
│  │ ChromaDB  │  │  │  │ GPT-4.1   │  │   │  │ mcp_rag_tools    │   │
│  │ (vectors) │  │  │  │ mini      │  │   │  │ template_tools   │   │
│  └───────────┘  │  │  └───────────┘  │   │  └──────────────────┘   │
│  ┌───────────┐  │  │  ┌───────────┐  │   └─────────────────────────┘
│  │ JSON Meta │  │  │  │ Embeddings │  │              │
│  │  (disk)   │  │  │  │  3-small  │  │              ▼
│  └───────────┘  │  │  └───────────┘  │   ┌─────────────────────────┐
└─────────────────┘  └─────────────────┘   │  GOOGLE SHEETS CACHE    │
                                           │  ┌──────────────────┐   │
                                           │  │ sheets_cache.py  │   │
                                           │  └──────────────────┘   │
                                           │          │              │
                                           │  ┌───────┴───────┐      │
                                           │  ▼               ▼      │
                                           │ Redis       Google      │
                                           │(optional)   Sheets API  │
                                           └─────────────────────────┘
```

### LangGraph Workflow Nodes

1. **retrieve_context** - Fetches conversation summary from memory
2. **agent** - Calls LLM with system prompt + tools
3. **tools** - Executes any tool calls (async)
4. **summarize** - Creates summaries every N turns
5. **end** - Completes conversation turn

### Data Flow

```
User Message
     │
     ▼
┌─────────────────┐
│ Load History    │ ← conversations_metadata.json
└─────────────────┘
     │
     ▼
┌─────────────────┐
│ Build Context   │ ← Summary + Stage Context
└─────────────────┘
     │
     ▼
┌─────────────────┐
│ Call LLM        │ → System Prompt + User Message + Tools
└─────────────────┘
     │
     ▼
┌─────────────────┐
│ Execute Tools?  │ → fetch_course_details, fetch_faqs, etc.
└─────────────────┘
     │
     ▼
┌─────────────────┐
│ Generate        │ → Final response text
│ Response        │
└─────────────────┘
     │
     ▼
┌─────────────────┐
│ Save Turn       │ → conversations_metadata.json
└─────────────────┘
     │
     ▼
┌─────────────────┐
│ Summarize?      │ → Every N turns, create summary
└─────────────────┘
     │
     ▼
Response to User
```

---

## 5. Core Modules Deep Dive

### 5.1 app.py - FastAPI Application

**Location:** `app.py` (915 lines)

**Responsibilities:**
- FastAPI app initialization with lifespan management
- API endpoint definitions
- Middleware configuration (CORS, trusted hosts)
- Request/response validation
- API key authentication

**Key Components:**

```python
# Lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize agent, cache, memory
    global intelligent_agent, cache_service
    cache_service = GoogleSheetsCacheService()
    await cache_service.preload_all_sheets()
    intelligent_agent = IntelligentChatAgent(cache_service=cache_service)
    yield
    # Shutdown: Cleanup

# Authentication dependency
async def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != os.getenv("API_KEY"):
        raise HTTPException(status_code=401)
```

**Request Models:**
- `ChatRequest` - message, conversation_id, stream
- `WebhookPayload` - spreadsheet_id, sheet_name, action, timestamp

**Response Models:**
- `ChatResponse` - response, conversation_id, turn_count, context_used, stage
- `HealthResponse` - status, agent_initialized, memory_db_path, etc.

---

### 5.2 core/agent.py - LangGraph Agent

**Location:** `core/agent.py` (659 lines)

**Class: IntelligentChatAgent**

```python
class IntelligentChatAgent:
    def __init__(
        self,
        model_name: str = "gpt-4.1-mini",
        temperature: float = 0.7,
        memory_db_path: str = "./memory_db",
        cache_service: GoogleSheetsCacheService = None,
        summarize_interval: int = 10
    ):
        self.llm = ChatOpenAI(model=model_name, temperature=temperature)
        self.memory = LongTermMemory(db_path=memory_db_path)
        self.cache_service = cache_service
        self.summarize_interval = summarize_interval
        self.all_tools = self._create_tools()
        self.app = self._create_graph()
```

**State Definition:**
```python
class AgentState(TypedDict):
    messages: List[BaseMessage]      # Conversation messages
    conversation_id: str             # UUID for conversation
    turn_count: int                  # Current turn number
    context: List[Dict]              # Retrieved context
```

**Main Method - chat():**
```python
async def chat(self, message: str, conversation_id: str = None) -> ChatResponse:
    # 1. Load or create conversation
    # 2. Get history from memory
    # 3. Build initial state
    # 4. Run graph workflow
    # 5. Extract response
    # 6. Save turn to memory
    # 7. Return ChatResponse
```

**System Prompt Loading:**
- Loaded once at startup from `config/prompt.txt`
- Cached in `self.system_prompt`
- Injected with conversation summary and stage context per request

---

### 5.3 core/memory.py - Long-Term Memory

**Location:** `core/memory.py` (628 lines)

**Class: LongTermMemory**

```python
class LongTermMemory:
    def __init__(self, db_path: str = "./memory_db"):
        self.db_path = db_path
        self.embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            dimensions=512
        )
        self.vectorstore = Chroma(
            collection_name="conversations",
            embedding_function=self.embeddings,
            persist_directory=db_path
        )
        self.conversations_metadata = self._load_metadata()
        self._lock = threading.Lock()
```

**Key Methods:**

| Method | Purpose |
|--------|---------|
| `add_conversation(conv_id, user_msg, asst_msg)` | Add turn to metadata |
| `add_summary(conv_id, summary)` | Embed and store summary |
| `get_conversation_history(conv_id, limit)` | Get all turns |
| `get_conversation_summary(conv_id)` | Get summary text |
| `update_stage(conv_id, stage)` | Update lead stage |
| `update_lead_data(conv_id, data)` | Update lead info |
| `get_leads_by_stage(stage)` | Filter by stage |
| `get_all_stage_stats()` | Get funnel analytics |

**Metadata JSON Structure:**
```json
{
  "{conversation_id}": {
    "created_at": "ISO8601",
    "updated_at": "ISO8601",
    "stage": "COURSE_SELECTED",
    "stage_updated_at": "ISO8601",
    "summary": "User selected CTA course...",
    "turns": [
      {
        "timestamp": "ISO8601",
        "user_message": "...",
        "assistant_message": "..."
      }
    ],
    "lead_data": {
      "name": "...",
      "email": "...",
      "phone": "...",
      "selected_course": "...",
      "education_level": "...",
      "goal_motivation": "..."
    }
  }
}
```

**Storage Limits:**
- Max 100 turns per conversation in metadata
- Only summaries are embedded (not individual turns)
- Thread-safe with locks
- Windows-compatible atomic writes

---

### 5.4 core/sheets_cache.py - Google Sheets Cache

**Location:** `core/sheets_cache.py` (687 lines)

**Class: GoogleSheetsCacheService**

```python
class GoogleSheetsCacheService:
    def __init__(self):
        self.sheets_client = self._authenticate()
        self.redis_client = self._init_redis()  # Optional
        self.vector_stores = {}  # Per-sheet ChromaDB
        self.embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            dimensions=512
        )
        self._in_memory_cache = {}  # Fallback
```

**Authentication Methods:**

1. **OAuth2** (Primary for production):
```python
# Requires: GOOGLE_SHEETS_CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN
Credentials(
    token=access_token,
    refresh_token=refresh_token,
    client_id=client_id,
    client_secret=client_secret
)
```

2. **Service Account** (Alternative):
```python
# Requires: GOOGLE_SHEETS_CREDENTIALS_PATH
service_account.Credentials.from_service_account_file(path)
```

**Cached Sheets:**
- `Course_Details` - Fees, duration, dates, professors
- `Course_Links` - Demo links, PDF links, course pages
- `FAQs` - Common questions and answers
- `About_Profr` - Professor/trainer information
- `Company_Info` - Contact details, locations

**Cache Strategy:**
1. **Redis** (primary) - Fast key-value storage
2. **In-Memory** (fallback) - If Redis unavailable
3. **ChromaDB** - Semantic search on FAQs

**Key Methods:**
```python
async def get_sheet_data(sheet_name: str) -> List[List]
async def search_sheet_data(query: str, sheet_name: str, k: int) -> List
async def sync_sheet(sheet_name: str) -> bool
async def preload_all_sheets() -> None
```

---

### 5.5 core/context_injector.py - Stage-Based Context

**Location:** `core/context_injector.py`

**Purpose:** Proactively inject relevant data based on conversation stage

**Stage Context Map:**
```python
STAGE_CONTEXT = {
    "NEW": [],
    "NAME_COLLECTED": [],
    "COURSE_SELECTED": ["Course_Details", "Course_Links"],
    "EDUCATION_COLLECTED": ["Course_Details"],
    "GOAL_COLLECTED": ["Course_Details", "FAQs"],
    "DEMO_SHARED": ["Course_Links", "Company_Info"],
    "ENROLLED": ["Company_Info"],
    "LOST": ["Company_Info"]
}
```

**Benefit:** Reduces tool calls by pre-loading relevant data

---

## 6. Tools System

### 6.1 Google Sheets Tools (tools/sheets_tools.py)

**5 LangChain Tools:**

#### fetch_course_details
```python
@tool
def fetch_course_details(course_name: str, field: str = None) -> str:
    """
    Fetch course details from Google Sheets.

    Args:
        course_name: Name of the course (e.g., "CTA", "ATO")
        field: Specific field (Fee, Duration, Start_Date, Professor, Locations)

    Returns:
        Course details or specific field value
    """
```

#### fetch_course_links
```python
@tool
def fetch_course_links(course_name: str, link_type: str = None) -> str:
    """
    Fetch course links from Google Sheets.

    Args:
        course_name: Name of the course
        link_type: Type of link (Demo_Link, Pdf_Link, Course_Page_Link)

    Returns:
        Links for the course
    """
```

#### fetch_faqs
```python
@tool
def fetch_faqs(query: str = None, top_k: int = 5) -> str:
    """
    Search FAQs using semantic search.

    Args:
        query: Search query (optional)
        top_k: Number of results to return

    Returns:
        Top matching FAQs
    """
```

#### fetch_professor_info
```python
@tool
def fetch_professor_info(professor_name: str = None, course_name: str = None) -> str:
    """
    Fetch professor/trainer information.

    Args:
        professor_name: Name of professor (optional)
        course_name: Course name to find professor for (optional)

    Returns:
        Professor bio, qualifications, experience
    """
```

#### fetch_company_info
```python
@tool
def fetch_company_info(field: str = None) -> str:
    """
    Fetch company information.

    Args:
        field: Specific field (Contact, Website, Campuses, Feedback_Link)

    Returns:
        Company information
    """
```

---

### 6.2 MCP RAG Tool (tools/mcp_rag_tools.py)

**Purpose:** Save lead data to external MCP endpoint BEFORE sharing demo video

```python
@tool
def append_lead_to_rag_sheets(
    name: str,
    email: str = None,
    phone: str = None,
    company: str = None,
    notes: str = None,
    metadata: dict = None
) -> str:
    """
    Save lead information to external MCP RAG endpoint.

    CRITICAL: Must be called BEFORE sharing demo video (Step 6).

    Returns:
        Confirmation message (does NOT return links or course info)
    """
```

**Endpoint:** Configured via `MCP_RAG_SHEETS_URL` env var
**Default:** `https://www.ictpk.cloud/mcp/rag-sheets`

---

### 6.3 Template Tools (tools/template_tools.py)

```python
@tool
def get_message_template(template_name: str, language: str = "english") -> str:
    """
    Retrieve a message template.

    Args:
        template_name: Name of template (e.g., "GREETING_NEW_LEAD")
        language: "english", "urdu", or "mixed"

    Returns:
        Template text with placeholders like {name}, {Pdf_Link}
    """

@tool
def list_available_templates() -> str:
    """
    List all available message templates.

    Returns:
        List of template names and descriptions
    """
```

---

## 7. Configuration Files

### 7.1 Environment Variables (.env.example)

**Required Variables:**
```bash
# OpenAI (Required)
OPENAI_API_KEY=sk-...

# API Security (Required)
API_KEY=your-api-key-here

# Google Sheets (Required - choose one auth method)
## OAuth2 Method:
GOOGLE_SHEETS_CLIENT_ID=...
GOOGLE_SHEETS_CLIENT_SECRET=...
GOOGLE_SHEETS_REFRESH_TOKEN=...

## OR Service Account Method:
GOOGLE_SHEETS_CREDENTIALS_PATH=/path/to/credentials.json

# Google Sheets Config (Required)
GOOGLE_SHEETS_SPREADSHEET_ID=your-spreadsheet-id
GOOGLE_SHEETS_SHEET_NAMES=Course_Details,Course_Links,FAQs,About_Profr,Company_Info
```

**Optional Variables:**
```bash
# Redis (Optional - falls back to in-memory)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0

# LLM Configuration
MODEL_NAME=gpt-4.1-mini
TEMPERATURE=0.7

# Memory & Storage
MEMORY_DB_PATH=/app/memory_db
CHROMA_DB_PATH=/app/sheets_index_db
SUMMARIZE_INTERVAL=10

# API Server
API_HOST=0.0.0.0
API_PORT=8009
ENVIRONMENT=production
WORKERS=4

# Webhook
SHEETS_WEBHOOK_ENABLED=true
SHEETS_WEBHOOK_SECRET=your-webhook-secret
SHEETS_FALLBACK_POLL_ENABLED=true
SHEETS_FALLBACK_POLL_INTERVAL=86400

# External Integration
MCP_RAG_SHEETS_URL=https://www.ictpk.cloud/mcp/rag-sheets
```

---

### 7.2 System Prompt (config/prompt.txt)

**Structure (772+ lines):**

1. **SECTION 1: Core Identity**
   - Name: Tanveer Awan
   - Role: Enrollment Advisor
   - Gender: Male

2. **SECTION 2: Critical Rules**
   - RULE #1: Always fetch data from Google Sheets (never from memory)
   - RULE #2: Data retrieval decision tree
   - RULE #3: Max 70 words per response
   - RULE #4: Language matching (English/Roman Urdu/Mixed)
   - RULE #5: Remember within current conversation
   - RULE #6: Never make up information
   - RULE #7: Save lead data before demo video

3. **SECTION 3: Conversation Flow (8 Steps)**
   - Step 1: Greeting & name collection
   - Step 2: Course selection
   - Step 3: Education background
   - Step 4: Goals/motivation
   - Step 5: Validation + PDF sharing
   - Step 6: Demo video + lead capture
   - Step 7: Answer questions
   - Step 8: Enrollment

4. **SECTION 4: Message Templates System**

5. **SECTION 5: Forbidden Actions**
   - Never admit being AI
   - Never make up data
   - Never push for payment

6. **SECTION 6: Mandatory Actions**

7. **SECTION 7: Validation Checklist (12 points)**

8. **SECTION 8: Reference Data**
   - Bank details
   - Contact numbers
   - Campus addresses

9. **SECTION 9-14:** Additional rules and special cases

---

### 7.3 Message Templates (config/templates.json)

**Format:**
```json
{
  "TEMPLATE_NAME": {
    "description": "Human-readable description",
    "english": "Template in English with {placeholders}",
    "urdu": "Template in Roman Urdu",
    "mixed": "Template mixing both (optional)"
  }
}
```

**Key Templates (40+):**
- `GREETING_NEW_LEAD` - Initial greeting
- `GREETING_RETURNING_LEAD` - Welcome back
- `COURSE_SELECTION` - List all 12 courses
- `EDUCATION_INQUIRY` - Ask about education
- `GOAL_INQUIRY` - Ask about goals
- `VALIDATION_WITH_PDF` - Share course PDF
- `DEMO_VIDEO_SHARE` - Share demo link
- `FEE_INQUIRY` - Fee information
- `BATCH_DETAILS` - Batch schedule
- `TRAINER_INFO` - Professor details
- `PAYMENT_DETAILS` - Bank account info
- `DATA_NOT_FOUND` - Generic fallback
- `NON_ICT_TOPIC` - Off-topic redirect
- `AI_ACCUSATION` - Response to "are you AI?"

---

## 8. Data Models & Schemas

### 8.1 ChromaDB Collections

**Collection: conversations**
```
Documents:
  - id: "conv_{conversation_id}_{timestamp}"
  - content: "Conversation Summary: {summary_text}"
  - embedding: [512-dimensional vector]
  - metadata: {conversation_id, timestamp, type: "summary"}
```

**Collection: {sheet_name}_index** (per sheet)
```
Documents:
  - id: "row_{index}"
  - content: "Row data as formatted text"
  - embedding: [512-dimensional vector]
  - metadata: {sheet_name, row_index, timestamp}
```

### 8.2 Redis Cache Schema

```
Key: "{sheet_name}:data"
Value: JSON array of all rows

Key: "{sheet_name}:timestamp"
Value: Last sync timestamp

Key: "FAQs:search:{query_hash}"
Value: JSON search results
TTL: 1 hour
```

### 8.3 Pydantic Models

**Request:**
```python
class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    stream: bool = False

class WebhookPayload(BaseModel):
    spreadsheet_id: str
    sheet_name: str
    action: str
    timestamp: str
```

**Response:**
```python
class ChatResponse(BaseModel):
    response: str
    conversation_id: str
    turn_count: int
    context_used: List[Dict]
    stage: str
    lead_data: Optional[Dict]
    timestamp: str

class HealthResponse(BaseModel):
    status: str
    agent_initialized: bool
    memory_db_path: str
    sheets_cache_initialized: bool
    redis_connected: bool
    version: str
```

---

## 9. API Reference

### Public Endpoints (No Auth)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Root info, version, docs link |
| GET | `/health` | Health check with system status |
| GET | `/debug/sheets` | Debug Google Sheets connection |

### Protected Endpoints (API Key Required)

**Header:** `X-API-Key: {your-api-key}`

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/chat` | Send message to agent |
| GET | `/conversations` | List all conversations |
| GET | `/conversations/{id}` | Get conversation history |
| GET | `/conversations/{id}/summary` | Get conversation summary |
| POST | `/conversations/{id}/search` | Semantic search in conversation |
| GET | `/conversations/{id}/stage` | Get current lead stage |
| POST | `/conversations/{id}/update-stage` | Manually update stage |
| GET | `/leads/by-stage/{stage}` | Filter leads by stage |
| GET | `/leads/stats` | Get lead statistics |

### Webhook Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/webhooks/google-sheets-update` | X-Webhook-Secret | Real-time sheet sync |

### Example Requests

**Chat:**
```bash
curl -X POST http://localhost:8009/chat \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"message": "I want to enroll in CTA course"}'
```

**Health Check:**
```bash
curl http://localhost:8009/health
```

---

## 10. External Integrations

### 10.1 Google Sheets API

**API Version:** v4
**Scopes:** `https://www.googleapis.com/auth/spreadsheets.readonly`

**Authentication:**
1. OAuth2 with refresh token
2. Service account JSON credentials

**Data Source:** Single Google Spreadsheet with multiple sheets

### 10.2 OpenAI API

**Models Used:**
- Chat: `gpt-4.1-mini` (128k context)
- Embeddings: `text-embedding-3-small` (512 dimensions)

**Endpoints:**
- `/v1/chat/completions`
- `/v1/embeddings`

### 10.3 Redis

**Purpose:** Fast cache for Google Sheets data
**Connection Pool:** Max 50 connections
**Health Check:** Every 30 seconds
**Fallback:** In-memory cache if unavailable

### 10.4 MCP RAG Endpoint

**Default URL:** `https://www.ictpk.cloud/mcp/rag-sheets`
**Purpose:** Save lead data before demo video
**Method:** POST with lead information

---

## 11. Execution Flow

### 11.1 Application Startup

```
1. Load environment variables
2. Validate OPENAI_API_KEY
3. Initialize GoogleSheetsCacheService
   └── Authenticate with Google Sheets API
   └── Connect to Redis (if available)
   └── Pre-load all configured sheets
4. Initialize IntelligentChatAgent
   └── Load system prompt from config/prompt.txt
   └── Initialize OpenAI LLM
   └── Create tools (sheets, MCP, templates)
   └── Build LangGraph workflow
   └── Initialize LongTermMemory
5. Start background tasks (fallback polling)
6. FastAPI ready to accept requests
```

### 11.2 Chat Request Processing

```
POST /chat
     │
     ▼
verify_api_key() ─── Invalid ──→ 401 Unauthorized
     │
     │ Valid
     ▼
IntelligentChatAgent.chat(message, conversation_id)
     │
     ▼
Load/Create Conversation
     │
     ▼
Get History from Memory
     │
     ▼
Build AgentState
     │
     ▼
Run LangGraph Workflow:
     │
     ├── retrieve_context ──→ Get summary from memory
     │
     ├── agent ──→ Call LLM with system prompt + tools
     │         └── LLM decides: respond or call tool?
     │
     ├── tools (if needed) ──→ Execute tool calls
     │         └── fetch_course_details, fetch_faqs, etc.
     │
     └── summarize (if turn_count % interval == 0)
               └── Create summary, embed in ChromaDB
     │
     ▼
Extract Final Response
     │
     ▼
Save Turn to Memory
     │
     ▼
Return ChatResponse
```

---

## 12. Deployment & Infrastructure

### 12.1 Docker

**Dockerfile:** Multi-stage build
- Stage 1 (builder): Install dependencies
- Stage 2 (runtime): Minimal image with app

**Key Features:**
- Non-root user execution
- Health checks configured
- Volume mounts for persistence
- ~200MB final image

### 12.2 Docker Compose

**Development:**
```bash
docker-compose up -d
```

**Production:**
```bash
docker-compose -f docker-compose.prod.yml up -d
```

### 12.3 CI/CD Pipeline

**File:** `.github/workflows/deploy.yml`

**Flow:**
1. Push to main/master
2. Build Docker image
3. Push to Docker Hub
4. Deploy to Hostinger VPS

**Required Secrets:**
- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`
- `HOSTINGER_API_KEY`
- `HOSTINGER_VM_ID`

---

## 13. Design Patterns & Optimizations

### 13.1 Patterns Used

- **State Machine:** LangGraph StateGraph for conversation flow
- **Repository Pattern:** Memory abstraction for data access
- **Factory Pattern:** Tool creation
- **Singleton:** Global agent and cache instances
- **Dependency Injection:** FastAPI dependencies for auth

### 13.2 Performance Optimizations

- System prompt cached at startup
- Only summaries embedded (not turns)
- Lazy loading of sheet data
- Redis connection pooling
- TTL-based context cache
- Limit 100 turns per conversation

### 13.3 Reliability Features

- Fallback polling for sheet sync
- Redis → in-memory fallback
- Thread-safe operations
- Windows-compatible file writes
- Graceful shutdown handling

---

## 14. Lead Pipeline & Stages

### 8 Stages

| Stage | Description | Transition Trigger |
|-------|-------------|-------------------|
| `NEW` | Fresh conversation | Initial message |
| `NAME_COLLECTED` | Got user's name | Name provided |
| `COURSE_SELECTED` | Course chosen | Course selection |
| `EDUCATION_COLLECTED` | Education known | Education shared |
| `GOAL_COLLECTED` | Goals understood | Goals discussed |
| `DEMO_SHARED` | Demo video sent | Demo link shared |
| `ENROLLED` | Successfully enrolled | Enrollment confirmed |
| `LOST` | Lead dropped off | Inactivity/rejection |

### Automatic Stage Tracking

Stages are updated based on conversation progress:
- Agent detects information collection
- Stages update automatically
- Manual override available via API

---

## 15. Message Templates System

### Template Retrieval

```python
# In agent conversation
template = get_message_template("GREETING_NEW_LEAD", "english")
# Returns: "Aoa!\nI am Tanveer Awan from ICT...\nMay I know your name?"
```

### Placeholder System

Templates use `{placeholders}`:
- `{name}` - Lead's name
- `{Pdf_Link}` - Course PDF link
- `{Demo_Link}` - Demo video link
- `{fee}` - Course fee
- `{duration}` - Course duration

### Language Options

- `english` - Full English
- `urdu` - Roman Urdu
- `mixed` - Both languages

---

## 16. Critical Rules & Constraints

### Non-Negotiable Rules

1. **Always fetch data from Google Sheets** - Never use memory for fees, dates, links
2. **Never admit being AI** - Always maintain Tanveer Awan persona
3. **Max 70 words per response** - Keep messages concise
4. **Save lead before demo** - Call `append_lead_to_rag_sheets` before sharing demo
5. **Match user's language** - Single language per message
6. **Never push for payment** - Only share payment info when asked
7. **Respectful "Ap" form** - Use formal Roman Urdu

### Forbidden Actions

- Making up course information
- Sharing payment details unprompted
- Discussing competitors
- Providing legal/tax advice
- Admitting AI nature
- Using casual language

---

## 17. Troubleshooting Guide

### Common Issues

**Issue:** Google Sheets connection fails
**Solution:** Check credentials, verify spreadsheet ID, ensure sheet names match

**Issue:** Redis connection timeout
**Solution:** Falls back to in-memory automatically; check Redis config if needed

**Issue:** Agent not responding
**Solution:** Check OpenAI API key, verify health endpoint

**Issue:** Webhook not triggering
**Solution:** Verify webhook secret, check Apps Script trigger

### Debug Endpoints

- `/health` - System status
- `/debug/sheets` - Google Sheets connection

### Log Locations

- Docker: `docker logs ict_agent`
- Local: Console output

---

## 18. Quick Reference

### Commands

```bash
# Development
uv run python scripts/run_api.py

# Docker Development
docker-compose up -d

# Docker Production
docker-compose -f docker-compose.prod.yml up -d

# OAuth2 Setup
python scripts/setup_oauth2.py
```

### Key Files

| File | Purpose |
|------|---------|
| `app.py` | API endpoints |
| `core/agent.py` | LangGraph agent |
| `core/memory.py` | Conversation storage |
| `core/sheets_cache.py` | Google Sheets cache |
| `config/prompt.txt` | System prompt |
| `config/templates.json` | Message templates |

### Environment Quick Setup

```bash
cp .env.example .env
# Edit .env with your values
# Required: OPENAI_API_KEY, API_KEY, GOOGLE_SHEETS_*
```

### Dependency Installation

```bash
# Using UV (recommended)
uv sync

# Using pip
pip install -e .
```

---

## Summary

**ICT Agent** is a production-ready WhatsApp enrollment chatbot for ICT courses. Key characteristics:

- **LangGraph-based** conversational agent with tool calling
- **Long-term memory** via ChromaDB + JSON metadata
- **Real-time data** from Google Sheets with Redis caching
- **8-stage lead pipeline** with automatic tracking
- **40+ message templates** for consistent responses
- **Docker-ready** with CI/CD to Hostinger

The agent maintains the persona of "Tanveer Awan", guides leads through enrollment, and integrates with external systems for lead capture. All course data is fetched in real-time from Google Sheets to ensure accuracy.

---

*Document generated for LLM knowledge transfer. Last updated: December 2025*
