<div align="center">

<a href="https://www.zensbot.com">
  <img src="https://i.ibb.co/zhynLp9G/90731ee7-407d-4fb0-873d-7ad75535e262.jpg" alt="Zensbot Logo" width="300"/>
</a>

# 🤖 ICT Enrollment Agent

[![Python](https://img.shields.io/badge/Python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com/)
[![LangChain](https://img.shields.io/badge/LangChain-0.3+-orange.svg)](https://www.langchain.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)

**AI-Powered Enrollment Advisor for Institute of Corporate & Taxation (ICT)**

*Developed with ❤️ by [Zensbot](https://www.zensbot.com)*

[Features](#-features) • [Architecture](#-architecture) • [Installation](#-installation) • [Deployment](#-deployment) • [API Docs](#-api-documentation) • [Contact](#-contact)

</div>

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Features](#-features)
- [Architecture](#-architecture)
- [Tech Stack](#-tech-stack)
- [Project Structure](#-project-structure)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Database Setup](#-database-setup)
- [Running the Application](#-running-the-application)
- [Deployment](#-deployment)
- [API Documentation](#-api-documentation)
- [System Prompt Guide](#-system-prompt-guide)
- [Testing](#-testing)
- [Contributing](#-contributing)
- [About Zensbot](#-about-zensbot)
- [Contact](#-contact)
- [License](#-license)

---

## 🎯 Overview

**ICT Enrollment Agent** is a production-ready, AI-powered conversational assistant designed to guide prospective students through the enrollment process for the Institute of Corporate & Taxation (ICT) in Pakistan. Built as an intelligent enrollment advisor, the agent operates primarily through **WhatsApp**, providing personalized course recommendations, answering queries, and managing lead data with long-term conversation memory.

### 🌟 Highlights

- **Persona**: "Muhammad Abid" - A real ICT enrollment advisor
- **Primary Channel**: WhatsApp-based conversations
- **Language Support**: Natural mix of English and Roman Urdu (Pakistani style)
- **Intelligence**: Contextual awareness with long-term memory
- **Database**: Real-time course, pricing, and instructor data from Supabase
- **Lead Management**: Automatic CRM integration with conversation tracking

---

## ✨ Features

### 🤝 Conversational Intelligence

- **Adaptive Personality**: Warm, intelligent, consultative approach (not scripted)
- **Long-Term Memory**: ChromaDB vector store for conversation context
- **Auto-Summarization**: Compresses long conversations for efficient context
- **Multi-Turn Conversations**: Maintains state across multiple interactions
- **Natural Language**: Understands various terminologies (diploma, certification, program, training, CPD)

### 📚 Course Management

- **12+ Courses**: Tax, accounting, and corporate courses
- **Multi-Mode Support**: Online and Onsite options with different pricing/instructors
- **Dynamic Pricing**: Real-time pricing from database (with 25% discount support)
- **Location-Based**: Physical campuses in Lahore, Islamabad, and Karachi
- **Course Details**: Fees, duration, instructors, start dates, benefits

### 🎓 Specialized Features

- **CTA Course Handling**: Special flow for Certified Tax Advisor with online/onsite variants
- **Discount Management**: Formatted discount pricing (Full Price vs. Discount Price)
- **Demo Sharing**: Automated demo video and PDF brochure links
- **Professor Info**: Detailed instructor qualifications and experience
- **FAQ System**: Full-text search for common questions

### 📊 Lead Tracking & CRM

- **Automatic Lead Capture**: Saves name, course, education, goals, phone
- **Lead Stages**: Tracks progression (NEW → ENROLLED/LOST)
- **Upsert Logic**: Creates or updates leads automatically
- **Conversation Metadata**: JSON-based conversation storage
- **Lead Analytics**: By stage, course, and timeline

### 🔧 Production-Ready

- **API Authentication**: X-API-Key header protection
- **Health Checks**: /health endpoint with Supabase connectivity
- **CORS Support**: Configurable trusted hosts
- **Docker Deployment**: Multi-stage build with non-root user
- **CI/CD Pipeline**: GitHub Actions auto-deployment
- **Graceful Shutdown**: 2-minute timeout for active requests
- **Nginx Integration**: Reverse proxy configuration included

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        User (WhatsApp)                          │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                     FastAPI REST API                            │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Endpoints: /chat, /conversations, /leads, /health       │  │
│  │  Auth: API Key (X-API-Key header)                        │  │
│  └──────────────────────────────────────────────────────────┘  │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    LangGraph Agent (core/agent.py)              │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Nodes:                                                   │  │
│  │  • retrieve_context → agent → tools → summarize          │  │
│  │                                                            │  │
│  │  State Management:                                        │  │
│  │  • SQLite Checkpointer (conversation persistence)        │  │
│  │  • Conversation ID tracking                              │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────┬──────────────────────┬──────────────────────┬─────────────┘
      │                      │                      │
      ▼                      ▼                      ▼
┌──────────────┐   ┌──────────────────┐   ┌──────────────────────┐
│  ChromaDB    │   │  OpenAI GPT-4.1  │   │  Supabase (PostgreSQL)│
│  (Vector DB) │   │  (LLM)           │   │                       │
│              │   │                  │   │  • course_details     │
│  • Long-term │   │  • Chat          │   │  • course_links       │
│    memory    │   │  • Summarization │   │  • faqs               │
│  • Embeddings│   │  • Tool calls    │   │  • about_professor    │
│  • Context   │   │                  │   │  • company_info       │
│    retrieval │   │                  │   │  • leads (CRM)        │
└──────────────┘   └──────────────────┘   └──────────────────────┘
```

### 🔄 Conversation Flow

1. **User Message** → FastAPI `/chat` endpoint
2. **Retrieve Context** → ChromaDB fetches relevant conversation history
3. **Agent Processing** → LangGraph processes with OpenAI GPT-4.1-mini
4. **Tool Execution** → Queries Supabase for courses, pricing, professors
5. **Response Generation** → Formats response with emojis and bullet points
6. **Memory Update** → Saves conversation to ChromaDB and SQLite
7. **Lead Tracking** → Updates lead data in Supabase
8. **Auto-Summarization** → Every N turns, compresses context

---

## 🛠️ Tech Stack

| Category | Technologies |
|----------|-------------|
| **Backend** | Python 3.13, FastAPI 0.115+ |
| **AI/ML** | LangChain 0.3+, LangGraph 1.0+, OpenAI GPT-4.1-mini |
| **Vector DB** | ChromaDB 0.5+ (embeddings & memory) |
| **Database** | Supabase (PostgreSQL) with trigram indexes |
| **Persistence** | SQLite (LangGraph checkpointer), JSON metadata |
| **Caching** | Redis (optional, for distributed deployments) |
| **API Framework** | FastAPI with Pydantic v2 validation |
| **Deployment** | Docker, Docker Compose, Nginx |
| **CI/CD** | GitHub Actions |
| **Package Manager** | uv (ultra-fast Python package installer) |

---

## 📁 Project Structure

```
ict_agent/
├── app.py                          # FastAPI application (940 lines)
├── core/
│   ├── agent.py                    # LangGraph agent workflow (937 lines)
│   ├── memory.py                   # ChromaDB long-term memory (610 lines)
│   ├── supabase_service.py         # Database service (324 lines)
│   ├── context_injector.py         # Stage-based context injection (152 lines)
│   └── template_manager.py         # Message template CRUD (303 lines)
├── tools/
│   ├── supabase_tools.py           # LLM tools for DB queries (517 lines)
│   ├── template_tools.py           # Template retrieval tool (191 lines)
│   └── sheets_tools.py             # Google Sheets integration (374 lines)
├── config/
│   └── prompt.txt                  # System prompt (1,500+ lines)
├── scripts/
│   ├── run_api.py                  # Production server launcher
│   ├── upload_courses_to_supabase.py
│   └── create_new_prompt.py
├── tests/
│   ├── test_supabase_connection.py
│   ├── test_lead_append.py
│   ├── test_course_fetch.py
│   └── test_pricing_response.py
├── docker/
│   ├── Dockerfile                  # Multi-stage production build
│   ├── docker-compose.yml          # Local development
│   └── docker-compose.prod.yml     # Production deployment
├── nginx/
│   └── nginx.conf                  # Reverse proxy config
├── .github/
│   └── workflows/
│       └── deploy.yml              # CI/CD pipeline
├── supabase_schema.sql             # Database schema with indexes
├── .env.example                    # Environment variable template (203 lines)
├── pyproject.toml                  # Python dependencies (uv)
├── .dockerignore
├── .gitignore
└── README.md                       # This file
```

**Total Lines of Code**: ~4,363 Python lines (core modules)

---

## 🚀 Installation

### Prerequisites

- **Python 3.13+** (required)
- **uv** package manager ([Install uv](https://github.com/astral-sh/uv))
- **Supabase** account ([Sign up](https://supabase.com))
- **OpenAI API Key** ([Get key](https://platform.openai.com/api-keys))
- **Docker** (optional, for containerized deployment)

### Step 1: Clone Repository

```bash
git clone https://github.com/yourusername/ict_agent.git
cd ict_agent
```

### Step 2: Install Dependencies

Using `uv` (recommended):
```bash
uv sync
```

Or using `pip`:
```bash
pip install -e .
```

### Step 3: Set Up Environment Variables

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
# OpenAI Configuration
OPENAI_API_KEY=sk-...your-key...

# API Security
API_KEY=your-secret-api-key-here

# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-anon-key

# Server Configuration
PORT=8000
WORKERS=4
HOST=0.0.0.0

# Model Configuration
MODEL_NAME=gpt-4.1-mini
TEMPERATURE=0.7
MAX_TOKENS=16384

# Memory Configuration
SUMMARIZE_INTERVAL=10
RECURSION_LIMIT=50

# Optional: Redis (for distributed deployments)
# REDIS_HOST=localhost
# REDIS_PORT=6379

# Optional: Google Sheets Integration
# GOOGLE_SHEETS_CREDENTIALS_FILE=credentials.json
# GOOGLE_SHEETS_SPREADSHEET_ID=your-sheet-id
```

---

## 💾 Database Setup

### Step 1: Create Supabase Project

1. Go to [Supabase Dashboard](https://supabase.com/dashboard)
2. Create a new project
3. Copy your `SUPABASE_URL` and `SUPABASE_KEY`

### Step 2: Run Database Schema

Execute the SQL schema in Supabase SQL Editor:

```bash
cat supabase_schema.sql
```

Copy and run in: **Supabase Dashboard → SQL Editor → New Query**

This creates:
- ✅ `course_details` - Course information, pricing, instructors
- ✅ `course_links` - Demo videos, PDFs, course pages
- ✅ `faqs` - Frequently asked questions with full-text search
- ✅ `about_professor` - Instructor qualifications and bios
- ✅ `company_info` - ICT contact numbers, locations
- ✅ `leads` - CRM lead tracking

### Step 3: Populate Sample Data

```bash
python scripts/upload_courses_to_supabase.py
```

---

## 🏃 Running the Application

### Development Mode

```bash
# Using uv
uv run python scripts/run_api.py

# Or directly with uvicorn
uvicorn app:app --reload --port 8000
```

### Production Mode

```bash
python scripts/run_api.py
```

Features:
- ✅ 4 worker processes (configurable)
- ✅ Graceful shutdown (2-minute timeout)
- ✅ Port availability checking
- ✅ Uvloop for non-Windows systems

### API Endpoints

Once running, visit:
- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health
- **Supabase Debug**: http://localhost:8000/debug/supabase

---

## 🐳 Deployment

### Docker Deployment (Recommended)

#### Development

```bash
docker-compose up --build
```

#### Production

```bash
docker-compose -f docker-compose.prod.yml up -d
```

Production features:
- ✅ Multi-stage build (optimized image size)
- ✅ Non-root user (appuser)
- ✅ Health checks (30s interval)
- ✅ Resource limits (4 CPU, 8GB RAM)
- ✅ JSON logging with rotation
- ✅ UTF-8 locale support

### Nginx Reverse Proxy

```bash
# Copy nginx config
sudo cp nginx/nginx.conf /etc/nginx/sites-available/ict_agent
sudo ln -s /etc/nginx/sites-available/ict_agent /etc/nginx/sites-enabled/

# Test and reload
sudo nginx -t
sudo systemctl reload nginx
```

### CI/CD with GitHub Actions

The project includes automated deployment:

**.github/workflows/deploy.yml**:
1. ✅ Builds Docker image on push to `main`/`master`
2. ✅ Pushes to Docker Hub (`kamilzafar/ict_agent:latest`)
3. ✅ Deploys to Hostinger VPS via SSH
4. ✅ SHA-tagged deployments for rollback

**Setup**:
```bash
# Add GitHub Secrets:
# - DOCKER_USERNAME
# - DOCKER_PASSWORD
# - VPS_HOST
# - VPS_USERNAME
# - VPS_SSH_KEY
```

---

## 📡 API Documentation

### Authentication

All endpoints require `X-API-Key` header:

```bash
curl -H "X-API-Key: your-api-key" http://localhost:8000/health
```

### Key Endpoints

#### 1. **Chat** (Main Endpoint)

```http
POST /chat
Content-Type: application/json
X-API-Key: your-api-key

{
  "message": "CTA course ki fee kitni hai?",
  "conversation_id": "user_12345",
  "user_metadata": {
    "name": "Hassan",
    "phone": "+923001234567"
  }
}
```

**Response**:
```json
{
  "response": "Yes, we do offer CTA!\n\nDo you prefer online or onsite?\n\n💻 Online - Live online classes\n📍 Onsite - Physical campus classes in:\n   - Lahore (Model Town)\n   - Islamabad (I-10)\n   - Karachi (Shahrah-e-Faisal)",
  "conversation_id": "user_12345",
  "metadata": {
    "tokens_used": 1234,
    "model": "gpt-4.1-mini"
  }
}
```

#### 2. **Conversations**

```http
# List all conversations
GET /conversations

# Get specific conversation
GET /conversations/{conversation_id}

# Search conversation context
POST /conversations/{conversation_id}/search
{
  "query": "pricing"
}

# Get conversation summary
GET /conversations/{conversation_id}/summary
```

#### 3. **Leads**

```http
# Get leads by stage
GET /leads/by-stage/NEW
GET /leads/by-stage/ENROLLED

# Get lead statistics
GET /leads/stats
```

#### 4. **Health & Debug**

```http
# Health check
GET /health

# Supabase connectivity debug
GET /debug/supabase

# Clear cache (no-op with direct DB)
POST /admin/cache/clear
```

---

## 📝 System Prompt Guide

The agent's behavior is controlled by `config/prompt.txt` (1,500+ lines).

### Key Sections:

1. **Core Identity**: Defines "Muhammad Abid" persona
2. **Terminology Guide**: Maps diploma/certification/program → courses
3. **Discount Pricing Format**: Full price vs. discount price display
4. **CTA Special Handling**: Online/Onsite variant flow
5. **Response Formatting**: Bullet points with emojis
6. **Tool Usage Guide**: When to use which Supabase tool
7. **Conversation Flow**: Phase-by-phase progression
8. **Forbidden Actions**: 32 critical rules to avoid

### Editing the Prompt

```bash
# Direct edit
nano config/prompt.txt

# Or use the prompt creation script
python scripts/create_new_prompt.py
```

**Important**: Changes to `prompt.txt` require server restart.

---

## 🧪 Testing

### Run All Tests

```bash
# Test Supabase connection
python tests/test_supabase_connection.py

# Test lead data append
python tests/test_lead_append.py

# Test course fetching
python tests/test_course_fetch.py

# Test pricing response
python tests/test_pricing_response.py
```

### Manual Testing

```bash
# Chat endpoint
curl -X POST http://localhost:8000/chat \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "CTA ki fee kitni hai?",
    "conversation_id": "test_user_1"
  }'

# Health check
curl http://localhost:8000/health

# Supabase debug
curl http://localhost:8000/debug/supabase
```

---

## 🎨 Key Features Showcase

### 1. **Intelligent Course Handling**

```
User: "Do you have CTA diploma?"

Agent: "Yes, we do offer CTA!

Do you prefer online or onsite?

💻 Online - Live online classes
📍 Onsite - Physical campus classes in:
   - Lahore (Model Town)
   - Islamabad (I-10)
   - Karachi (Shahrah-e-Faisal)"
```

### 2. **Formatted Discount Pricing**

```
User: "I want my 25% discount for ICT Course"

Agent: "🎉 Congratulations! You've secured a 25% exclusive discount..."

User: "CTA online"

Agent: "CTA - Online:

💵 Full Price: 60,000 PKR
🎉 Discount Price: 45,000 PKR (25% OFF)

📅 Duration: 4 months
👨‍🏫 Instructor: Sir Rai Basharat Ali

You save: 15,000 PKR! 💰"
```

### 3. **Long-Term Memory**

The agent remembers:
- ✅ User's name
- ✅ Selected course
- ✅ Education level
- ✅ Goals
- ✅ Previous questions
- ✅ Conversation stage

### 4. **Automatic Lead Tracking**

Every interaction updates the CRM:
```sql
leads table:
- lead_name: "Hassan"
- phone_number: "+923001234567"
- course_selected: "Certified Tax Advisor - Online"
- education: "Bachelors"
- why_course: "Start own tax consultancy"
- status: "DEMO_SHARED"
- timestamp: "2026-01-02 14:30:00"
```

---

## 🤝 Contributing

We welcome contributions! Here's how:

### 1. Fork the Repository

```bash
git clone https://github.com/yourusername/ict_agent.git
cd ict_agent
git checkout -b feature/your-feature-name
```

### 2. Make Changes

- Follow Python PEP 8 style guide
- Add docstrings to functions
- Update tests if needed
- Keep prompt.txt organized

### 3. Test Your Changes

```bash
# Run tests
python tests/test_*.py

# Test locally
uv run python scripts/run_api.py
```

### 4. Submit Pull Request

```bash
git add .
git commit -m "Add: your feature description"
git push origin feature/your-feature-name
```

Then open a PR on GitHub!

---

## 🏢 About Zensbot

<div align="center">

<a href="https://www.zensbot.com">
  <img src="https://i.ibb.co/zhynLp9G/90731ee7-407d-4fb0-873d-7ad75535e262.jpg" alt="Zensbot Logo" width="250"/>
</a>

**Zensbot** is a leading AI automation and chatbot development company specializing in intelligent conversational agents for businesses across Pakistan and beyond.

### Our Services

🤖 **AI Chatbots** | 💬 **WhatsApp Automation** | 🎯 **Lead Generation** | 📊 **CRM Integration** | 🧠 **LLM Solutions**

</div>

### Why Zensbot?

- ✅ **Custom AI Solutions**: Tailored to your business needs
- ✅ **Production-Ready**: Built for scale and reliability
- ✅ **Long-Term Support**: Ongoing maintenance and updates
- ✅ **Local Expertise**: Understanding Pakistani market and language
- ✅ **Proven Track Record**: Trusted by leading institutions

### Our Projects

- 🎓 **ICT Enrollment Agent** (This project)
- 🏥 Healthcare Appointment Bots
- 🏪 E-commerce Customer Support
- 💼 B2B Lead Qualification Agents
- 📚 Educational Content Delivery

---

## 📞 Contact

<div align="center">

### Get in Touch with Zensbot

[![Website](https://img.shields.io/badge/Website-www.zensbot.com-blue?style=for-the-badge&logo=google-chrome)](https://www.zensbot.com)
[![Email](https://img.shields.io/badge/Email-hassan@zensbot.com-red?style=for-the-badge&logo=gmail)](mailto:hassan@zensbot.com)

### Our Team

**Hassan Arshad** - Founder & CEO
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0077B5?style=for-the-badge&logo=linkedin)](https://www.linkedin.com/in/hassanarshadd/)

**Kamil Zafar** - Co-Founder & CTO
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0077B5?style=for-the-badge&logo=linkedin)](https://www.linkedin.com/in/kamil-zafar/)

---

### Business Inquiries

📧 **General**: hassan@zensbot.com
🌐 **Website**: [www.zensbot.com](https://www.zensbot.com)
💼 **LinkedIn**: [Zensbot Company Page](https://www.linkedin.com/company/zensbot)

</div>

---

## 📄 License

```
MIT License

Copyright (c) 2026 Zensbot - AI Automation Solutions

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 🙏 Acknowledgments

- **OpenAI** - For GPT models and embeddings
- **LangChain Team** - For the amazing LangChain framework
- **Supabase** - For the robust PostgreSQL backend
- **FastAPI** - For the high-performance API framework
- **ICT Pakistan** - For trusting Zensbot with their enrollment automation

---

## 🎯 Future Roadmap

- [ ] Multi-language support (Urdu script)
- [ ] Voice message support (WhatsApp audio)
- [ ] Payment gateway integration
- [ ] Video call scheduling
- [ ] Advanced analytics dashboard
- [ ] Mobile app integration
- [ ] Multi-channel support (Telegram, Messenger)
- [ ] A/B testing for prompts

---

<div align="center">

### ⭐ Star Us on GitHub!

If you find this project useful, please consider giving it a star ⭐

---

<a href="https://www.zensbot.com">
  <img src="https://i.ibb.co/zhynLp9G/90731ee7-407d-4fb0-873d-7ad75535e262.jpg" alt="Zensbot Logo" width="200"/>
</a>

**Built with ❤️ by [Zensbot](https://www.zensbot.com)**

*Empowering businesses with intelligent automation*

</div>
