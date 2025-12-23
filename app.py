"""FastAPI application for the intelligent chat agent."""
import os
import logging
import asyncio
import sys
import time
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from pathlib import Path
import secrets


from fastapi import FastAPI, HTTPException, status, Request, Header, Depends, Security, Cookie, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv

from core.agent import IntelligentChatAgent
from core.supabase_service import SupabaseService

# Load environment variables
load_dotenv()

# Configure logging with production-ready settings
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger(__name__)

# Global agent instance
agent: Optional[IntelligentChatAgent] = None

# Global Supabase service instance
supabase_service: Optional[SupabaseService] = None

# API Key Security
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

def verify_api_key(api_key: Optional[str] = Security(API_KEY_HEADER)) -> bool:
    """Verify API key from request header.
    
    Args:
        api_key: API key from X-API-Key header
        
    Returns:
        True if API key is valid
        
    Raises:
        HTTPException: If API key is missing or invalid
    """
    expected_api_key = os.getenv("API_KEY")
    
    # API_KEY must be set in environment
    if not expected_api_key:
        logger.error("API_KEY not set in environment. API protection is disabled. Please set API_KEY environment variable.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API key authentication is not configured. Please set API_KEY environment variable.",
        )
    
    # API key must be provided in request
    if not api_key:
        logger.warning("API key missing from request")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is required. Please provide X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    # Validate API key
    if api_key != expected_api_key:
        logger.warning(f"Invalid API key attempted: {api_key[:10] if len(api_key) > 10 else '***'}...")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    return True


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI app."""
    global agent, supabase_service
    
    # Startup: Initialize agent
    logger.info("Initializing AI agent...")
    
    # Check for required environment variables
    if not os.getenv("OPENAI_API_KEY"):
        error_msg = "OPENAI_API_KEY environment variable is not set"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    # Check for API_KEY (required for API protection)
    if not os.getenv("API_KEY"):
        logger.warning("API_KEY environment variable is not set. API endpoints will be protected but will fail until API_KEY is configured.")
        logger.warning("Please set API_KEY environment variable to enable API authentication.")
    
    # Initialize Supabase service (if configured)
    try:
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")
        
        if supabase_url and supabase_key:
            logger.info("Initializing Supabase service...")
            try:
                supabase_service = SupabaseService(
                    supabase_url=supabase_url,
                    supabase_key=supabase_key
                )
                logger.info("✓ Supabase service initialized successfully")
            except Exception as supabase_error:
                # Supabase initialization failed - log warning but don't crash app
                logger.warning("=" * 70)
                logger.warning("⚠️  Supabase service initialization failed!")
                logger.warning(f"Error: {supabase_error}")
                logger.warning("The app will continue without Supabase.")
                logger.warning("")
                logger.warning("To fix Supabase configuration:")
                logger.warning("  1. Set SUPABASE_URL in .env (your Supabase project URL)")
                logger.warning("  2. Set SUPABASE_KEY in .env (your Supabase anon/service key)")
                logger.warning("  3. Verify credentials are correct")
                logger.warning("  4. Ensure database tables are created (course_links, course_details, faqs, professors, company_info)")
                logger.warning("  5. Restart the application after fixing credentials")
                logger.warning("=" * 70)
                supabase_service = None  # Set to None so agent can still initialize
        else:
            logger.info("Supabase not configured - skipping service initialization")
            logger.info("To enable Supabase, set:")
            logger.info("  - SUPABASE_URL (your Supabase project URL)")
            logger.info("  - SUPABASE_KEY (your Supabase anon/service key)")
            supabase_service = None
    except Exception as e:
        # Catch any unexpected errors and make Supabase optional
        logger.warning(f"Unexpected error during Supabase initialization: {e}", exc_info=True)
        logger.warning("Continuing without Supabase service")
        supabase_service = None
    
    try:
        agent = IntelligentChatAgent(
            model_name=os.getenv("MODEL_NAME", "gpt-4.1-mini"),  # Default to gpt-4.1-mini for 128k context window
            temperature=float(os.getenv("TEMPERATURE", "0.7")),
            memory_db_path=os.getenv("MEMORY_DB_PATH", "/app/memory_db"),
            summarize_interval=int(os.getenv("SUMMARIZE_INTERVAL", "10")),
            supabase_service=supabase_service
        )
        logger.info("Agent initialized successfully")
        logger.info(f"Model: {os.getenv('MODEL_NAME', 'gpt-4.1-mini')}")
        logger.info(f"Memory DB: {os.getenv('MEMORY_DB_PATH', '/app/memory_db')}")
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        raise
    except Exception as e:
        logger.error(f"Error initializing agent: {e}", exc_info=True)
        raise RuntimeError(f"Failed to initialize agent: {str(e)}") from e

    # Initialize template manager for admin interface
    try:
        from core.template_manager import TemplateManager
        global template_manager
        templates_path = os.path.join(os.path.dirname(__file__), "config", "templates.json")
        template_manager = TemplateManager(templates_path)
        logger.info("Template manager initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing template manager: {e}", exc_info=True)
        logger.warning("Admin template editor may not work correctly")
        template_manager = None

    yield
    
    # Shutdown: Cleanup
    logger.info("Shutting down...")


# ============================================================================
# Admin Session Management
# ============================================================================

# In-memory session storage (no expiration)
# Sessions persist until logout or server restart
# For production with multiple workers, consider using Redis
admin_sessions: set = set()  # session_id set (no expiration)


def create_session() -> str:
    """Create new admin session that never expires."""
    session_id = secrets.token_urlsafe(32)
    admin_sessions.add(session_id)
    return session_id


def validate_session(session_id: str) -> bool:
    """Validate admin session (no expiration check)."""
    return session_id in admin_sessions


def verify_admin_session(admin_session: Optional[str] = Cookie(None)):
    """Dependency for admin endpoints - validates session cookie."""
    logger.debug(f"Session validation - Cookie received: {admin_session is not None}")
    logger.debug(f"Active sessions count: {len(admin_sessions)}")

    if not admin_session:
        logger.warning("No session cookie provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session. Please login again."
        )

    if not validate_session(admin_session):
        logger.warning(f"Invalid session: {admin_session[:10]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session. Please login again."
        )

    logger.debug(f"Session validated successfully: {admin_session[:10]}...")
    return admin_session


# ============================================================================
# Create FastAPI app
# ============================================================================
# root_path is used when behind a proxy (e.g., nginx) with subpath
root_path = os.getenv("ROOT_PATH", "")
app = FastAPI(
    title="Intelligent Chat Agent API",
    description="Production-ready API for interacting with an AI agent with long-term memory and vector database search",
    version="1.0.0",
    lifespan=lifespan,
    root_path=root_path,  # For nginx proxy with subpath
    docs_url="/docs",  # Always enable docs
    redoc_url="/redoc",  # Always enable redoc
)

# Configure Trusted Host middleware for proxy security
# This ensures the app only accepts requests from trusted hosts
trusted_hosts = os.getenv("TRUSTED_HOSTS", "*").split(",")
if "*" not in trusted_hosts:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=trusted_hosts
)

# Configure CORS for production
allowed_origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if "*" not in allowed_origins else ["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Mount static files for admin UI
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
try:
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    logger.info(f"Static files mounted from: {static_dir}")
except Exception as e:
    logger.warning(f"Failed to mount static files: {e}")


# Serve admin UI HTML
@app.get("/admin", response_class=HTMLResponse, tags=["Admin"])
async def serve_admin_ui():
    """Serve the admin template editor interface."""
    admin_html_path = os.path.join(static_dir, "admin.html")
    if not os.path.exists(admin_html_path):
        return HTMLResponse(
            content="<h1>Admin UI Not Found</h1><p>Please create static/admin.html file.</p>",
            status_code=404
        )
    try:
        with open(admin_html_path, 'r', encoding='utf-8') as f:
            return HTMLResponse(content=f.read())
    except Exception as e:
        logger.error(f"Error serving admin UI: {e}")
        return HTMLResponse(
            content=f"<h1>Error</h1><p>Failed to load admin UI: {e}</p>",
            status_code=500
        )


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle unhandled exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred"}
    )


# Request/Response Models
class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    message: str = Field(..., description="User's message to the agent", min_length=1, max_length=10000)
    conversation_id: Optional[str] = Field(None, description="Conversation ID (creates new if not provided)", max_length=100)
    stream: bool = Field(False, description="Whether to stream the response")
    
    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        """Validate message is not empty after stripping."""
        if not v.strip():
            raise ValueError("Message cannot be empty")
        return v.strip()


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""
    response: str = Field(..., description="Agent's response")
    conversation_id: str = Field(..., description="Conversation ID")
    turn_count: int = Field(..., description="Current turn count in the conversation")
    context_used: List[Dict[str, Any]] = Field(default_factory=list, description="Relevant context retrieved from memory")
    stage: str = Field(default="NEW", description="Current stage of the lead")
    lead_data: Dict[str, Any] = Field(default_factory=dict, description="Collected lead information")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


class ConversationTurn(BaseModel):
    """Model for a single conversation turn."""
    timestamp: str
    user_message: str
    assistant_message: str


class ConversationHistory(BaseModel):
    """Response model for conversation history."""
    conversation_id: str
    created_at: str
    turns: List[ConversationTurn]
    summary: Optional[str] = None
    total_turns: int


class ConversationListResponse(BaseModel):
    """Response model for listing conversations."""
    conversations: List[Dict[str, Any]]
    total: int


class HealthResponse(BaseModel):
    """Response model for health check."""
    status: str
    agent_initialized: bool
    memory_db_path: str
    redis_connected: bool = False
    version: str = "1.0.0"


# Admin Template Editor Models
class LoginRequest(BaseModel):
    """Request model for admin login."""
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=100)


class TemplateUpdateRequest(BaseModel):
    """Request model for updating a template."""
    description: Optional[str] = None
    model_config = {"extra": "allow"}  # Allow dynamic language fields


class TemplateCreateRequest(BaseModel):
    """Request model for creating a new template."""
    name: str = Field(..., pattern="^[A-Z_]+$", description="Template name in UPPERCASE_SNAKE_CASE")
    description: str = Field(..., min_length=1, description="Template description")
    model_config = {"extra": "allow"}  # Allow dynamic language fields

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate template name is uppercase."""
        if not v.isupper():
            raise ValueError("Template name must be UPPERCASE_SNAKE_CASE")
        return v


# Routes
@app.get("/", tags=["Root"])
async def root():
    """Root endpoint."""
    return {
        "message": "Intelligent Chat Agent API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/debug/supabase", tags=["Debug"])
async def debug_supabase():
    """Debug endpoint to test Supabase connection."""
    if not supabase_service:
        return {
            "error": "Supabase service not initialized",
            "supabase_url": os.getenv("SUPABASE_URL", "Not set")
        }
    
    try:
        # Test connection by fetching a small amount of data
        test_courses = supabase_service.get_course_links()
        return {
            "status": "success",
            "supabase_url": os.getenv("SUPABASE_URL", "Not set"),
            "connection": "ok",
            "test_query": "successful",
            "cache_enabled": True,
            "realtime_enabled": os.getenv("SUPABASE_REALTIME_ENABLED", "true").lower() == "true"
        }
    except Exception as e:
        return {
            "status": "error",
            "supabase_url": os.getenv("SUPABASE_URL", "Not set"),
            "error": str(e),
            "error_type": type(e).__name__
        }


@app.post("/admin/cache/clear", tags=["Admin"], dependencies=[Depends(verify_api_key)])
async def clear_cache(table: Optional[str] = None):
    """Clear Supabase cache for instant updates after data changes.
    
    Use this endpoint after updating data in Supabase to see changes immediately.
    Note: If Realtime is enabled, cache clears automatically (no need to call this).
    
    Args:
        table: Optional table name (e.g., "course_links"), or None to clear all
    """
    if not supabase_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase service not initialized"
        )
    
    supabase_service.clear_cache(table)
    return {
        "status": "success",
        "message": f"Cache cleared for {table or 'all tables'}",
        "note": "Next query will fetch fresh data from Supabase"
    }


@app.get("/health", tags=["Health"], response_model=HealthResponse)
async def health_check():
    """Health check endpoint with comprehensive status."""
    supabase_connected = False
    if supabase_service:
        try:
            # Test connection with a simple query
            supabase_service.get_company_info()
            supabase_connected = True
        except Exception:
            supabase_connected = False
    
    return HealthResponse(
        status="healthy" if agent is not None else "degraded",
        agent_initialized=agent is not None,
        memory_db_path=os.getenv("MEMORY_DB_PATH", "./memory_db"),
        redis_connected=supabase_connected,  # Reusing field name for compatibility
        version="1.0.0"
    )


@app.post("/chat", tags=["Chat"], response_model=ChatResponse, dependencies=[Depends(verify_api_key)])
async def chat(request: ChatRequest):
    """Send a message to the agent and get a response.
    
    Args:
        request: Chat request containing message and optional conversation_id
    
    Returns:
        ChatResponse with agent's response and metadata
    
    Raises:
        HTTPException: If agent is not initialized or error occurs
    """
    if agent is None:
        logger.error("Agent not initialized")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent is not initialized"
        )
    
    try:
        logger.info(f"Processing chat request - conversation_id: {request.conversation_id}")
        
        # Process the message
        result = agent.chat(
            user_input=request.message,
            conversation_id=request.conversation_id
        )
        
        logger.info(f"Chat request completed - conversation_id: {result['conversation_id']}, turn: {result['turn_count']}")
        
        return ChatResponse(
            response=result["response"],
            conversation_id=result["conversation_id"],
            turn_count=result["turn_count"],
            context_used=result.get("context_used", []),
            stage=result.get("stage", "NEW"),
            lead_data=result.get("lead_data", {}),
            timestamp=datetime.now().isoformat()
        )
    
    except ValueError as e:
        logger.warning(f"Validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing message. Please try again."
        )


@app.get("/conversations/{conversation_id}", tags=["Conversations"], response_model=ConversationHistory, dependencies=[Depends(verify_api_key)])
async def get_conversation_history(conversation_id: str, limit: Optional[int] = None):
    """Get conversation history for a specific conversation ID.
    
    Args:
        conversation_id: Unique identifier for the conversation
        limit: Optional limit on number of turns to return
    
    Returns:
        ConversationHistory with all turns and summary
    
    Raises:
        HTTPException: If conversation not found or agent not initialized
    """
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent is not initialized"
        )
    
    try:
        # Get conversation history
        turns_data = agent.memory.get_conversation_history(conversation_id, limit=limit)
        
        if not turns_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conversation {conversation_id} not found"
            )
        
        # Get conversation metadata
        if conversation_id in agent.memory.conversations_metadata:
            metadata = agent.memory.conversations_metadata[conversation_id]
            created_at = metadata.get("created_at", "")
            summary = metadata.get("summary")
        else:
            created_at = turns_data[0]["timestamp"] if turns_data else datetime.now().isoformat()
            summary = None
        
        # Convert to response model
        turns = [
            ConversationTurn(
                timestamp=turn["timestamp"],
                user_message=turn["user_message"],
                assistant_message=turn["assistant_message"]
            )
            for turn in turns_data
        ]
        
        return ConversationHistory(
            conversation_id=conversation_id,
            created_at=created_at,
            turns=turns,
            summary=summary,
            total_turns=len(turns)
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving conversation: {str(e)}"
        )


@app.get("/conversations", tags=["Conversations"], response_model=ConversationListResponse, dependencies=[Depends(verify_api_key)])
async def list_conversations(limit: Optional[int] = 50):
    """List all conversations.
    
    Args:
        limit: Maximum number of conversations to return
    
    Returns:
        ConversationListResponse with list of conversations
    
    Raises:
        HTTPException: If agent is not initialized
    """
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent is not initialized"
        )
    
    try:
        conversations = []
        metadata = agent.memory.conversations_metadata
        
        for conv_id, conv_data in metadata.items():
            conversations.append({
                "conversation_id": conv_id,
                "created_at": conv_data.get("created_at", ""),
                "turn_count": len(conv_data.get("turns", [])),
                "summary": conv_data.get("summary"),
                "stage": conv_data.get("stage", "NEW"),
                "stage_updated_at": conv_data.get("stage_updated_at", "")
            })
        
        # Sort by created_at (newest first)
        conversations.sort(key=lambda x: x["created_at"], reverse=True)
        
        # Apply limit
        if limit:
            conversations = conversations[:limit]
        
        return ConversationListResponse(
            conversations=conversations,
            total=len(conversations)
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing conversations: {str(e)}"
        )


@app.get("/conversations/{conversation_id}/summary", tags=["Conversations"], dependencies=[Depends(verify_api_key)])
async def get_conversation_summary(conversation_id: str):
    """Get the summary for a specific conversation.
    
    Args:
        conversation_id: Unique identifier for the conversation
    
    Returns:
        Dictionary with conversation summary
    
    Raises:
        HTTPException: If conversation not found or agent not initialized
    """
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent is not initialized"
        )
    
    try:
        summary = agent.memory.get_conversation_summary(conversation_id)
        
        if summary is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conversation {conversation_id} not found or has no summary"
            )
        
        return {
            "conversation_id": conversation_id,
            "summary": summary
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving summary: {str(e)}"
        )


@app.post("/conversations/{conversation_id}/search", tags=["Conversations"], dependencies=[Depends(verify_api_key)])
async def search_conversation_context(
    conversation_id: str,
    query: str,
    k: int = 5
):
    """Search for relevant context within a conversation.
    
    Args:
        conversation_id: Unique identifier for the conversation
        query: Search query
        k: Number of results to return
    
    Returns:
        List of relevant document chunks
    
    Raises:
        HTTPException: If agent is not initialized
    """
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent is not initialized"
        )
    
    try:
        results = agent.memory.search_relevant_context(
            query=query,
            k=k,
            conversation_id=conversation_id
        )
        
        return {
            "conversation_id": conversation_id,
            "query": query,
            "results": [
                {
                    "content": doc.page_content,
                    "metadata": doc.metadata
                }
                for doc in results
            ],
            "count": len(results)
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error searching context: {str(e)}"
        )


@app.get("/leads/by-stage/{stage}", tags=["Leads"], dependencies=[Depends(verify_api_key)])
async def get_leads_by_stage(stage: str):
    """Get all leads in a specific stage.

    Args:
        stage: Stage to filter by (NEW, NAME_COLLECTED, COURSE_SELECTED, etc.)

    Returns:
        List of leads in that stage

    Raises:
        HTTPException: If agent is not initialized or invalid stage
    """
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent is not initialized"
        )

    valid_stages = list(agent.memory.STAGES.keys())

    if stage not in valid_stages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid stage. Must be one of: {valid_stages}"
        )

    try:
        leads = agent.memory.get_leads_by_stage(stage)

        return {
            "stage": stage,
            "count": len(leads),
            "leads": leads
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving leads: {str(e)}"
        )


@app.get("/leads/stats", tags=["Leads"], dependencies=[Depends(verify_api_key)])
async def get_lead_stats():
    """Get lead statistics across all stages.

    Returns:
        Statistics including counts per stage and conversion rate

    Raises:
        HTTPException: If agent is not initialized
    """
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent is not initialized"
        )

    try:
        stats = agent.memory.get_all_stage_stats()
        return stats

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving stats: {str(e)}"
        )


@app.post("/conversations/{conversation_id}/update-stage", tags=["Conversations"], dependencies=[Depends(verify_api_key)])
async def update_conversation_stage(conversation_id: str, new_stage: str):
    """Manually update a conversation's stage.

    Args:
        conversation_id: Unique identifier for the conversation
        new_stage: New stage to set

    Returns:
        Confirmation message with updated stage

    Raises:
        HTTPException: If agent is not initialized or invalid stage
    """
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent is not initialized"
        )

    try:
        agent.memory.manually_set_stage(conversation_id, new_stage)

        return {
            "message": "Stage updated successfully",
            "conversation_id": conversation_id,
            "new_stage": new_stage
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating stage: {str(e)}"
        )


@app.get("/conversations/{conversation_id}/stage", tags=["Conversations"], dependencies=[Depends(verify_api_key)])
async def get_conversation_stage(conversation_id: str):
    """Get the current stage and lead data for a conversation.

    Args:
        conversation_id: Unique identifier for the conversation

    Returns:
        Dictionary with stage and lead data

    Raises:
        HTTPException: If agent is not initialized
    """
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent is not initialized"
        )

    try:
        stage = agent.memory.get_stage(conversation_id)
        lead_data = agent.memory.get_lead_data(conversation_id)

        return {
            "conversation_id": conversation_id,
            "stage": stage,
            "lead_data": lead_data
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving stage: {str(e)}"
        )


# Note: Supabase doesn't need webhooks - data is always up-to-date in the database


# ============================================================================
# ADMIN ENDPOINTS - Template Editor
# ============================================================================

@app.post("/admin/login", tags=["Admin"])
async def admin_login(request: LoginRequest, response: Response):
    """
    Admin login endpoint for template editor.

    Validates credentials and creates a session cookie.
    """
    username = os.getenv("ADMIN_USERNAME", "ictxzensbot")
    password = os.getenv("ADMIN_PASSWORD", "ictxzensbot")

    if request.username != username or request.password != password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    # Create session
    session_id = create_session()

    # Set cookie with relaxed settings for nginx proxy compatibility
    # Note: Removed 'secure' flag to work with nginx SSL termination
    response.set_cookie(
        key="admin_session",
        value=session_id,
        httponly=True,
        samesite="lax",  # Lax for better compatibility with nginx proxy
        max_age=315360000,  # 10 years - essentially never expires
        path="/",  # Ensure cookie works for all paths
        domain=None  # Let browser determine domain automatically
    )

    logger.info(f"Admin login successful: {username}")
    logger.info(f"Session created: {session_id[:10]}... (total sessions: {len(admin_sessions)})")

    return {"success": True, "message": "Logged in successfully"}


@app.get("/admin/templates", tags=["Admin"])
async def list_templates(session: str = Depends(verify_admin_session)):
    """
    List all available templates.

    Returns template names, descriptions, and available languages.
    """
    try:
        if template_manager is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Template manager not initialized"
            )

        templates = template_manager.get_all_templates()

        result = []
        for name, data in templates.items():
            result.append({
                "name": name,
                "description": data.get("description", "No description"),
                "languages": [k for k in data.keys() if k != "description"]
            })

        return {"templates": result, "total": len(result)}

    except Exception as e:
        logger.error(f"Error listing templates: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list templates: {str(e)}"
        )


@app.get("/admin/templates/{name}", tags=["Admin"])
async def get_template(name: str, session: str = Depends(verify_admin_session)):
    """
    Get a single template by name.

    Returns all language versions and metadata for the template.
    """
    try:
        if template_manager is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Template manager not initialized"
            )

        template = template_manager.get_template(name)

        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Template '{name}' not found"
            )

        return {"name": name, **template}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting template {name}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get template: {str(e)}"
        )


@app.put("/admin/templates/{name}", tags=["Admin"])
async def update_template(
    name: str,
    data: TemplateUpdateRequest,
    session: str = Depends(verify_admin_session)
):
    """
    Update an existing template.

    Supports partial updates - only provided fields will be updated.
    Changes take effect immediately via hot-reload.
    """
    try:
        if template_manager is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Template manager not initialized"
            )

        # Get update data (exclude unset fields)
        update_data = data.model_dump(exclude_unset=True)

        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No update data provided"
            )

        # Update template
        template_manager.update_template(name, update_data)

        logger.info(f"Template updated by admin: {name}")

        return {
            "success": True,
            "message": f"Template '{name}' updated successfully",
            "reloaded": True
        }

    except ValueError as e:
        # Template not found
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating template {name}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Update failed: {str(e)}"
        )


@app.post("/admin/templates", tags=["Admin"], status_code=status.HTTP_201_CREATED)
async def create_template(
    data: TemplateCreateRequest,
    session: str = Depends(verify_admin_session)
):
    """
    Create a new template.

    Template name must be UPPERCASE_SNAKE_CASE and unique.
    Requires at least a description and one language version.
    """
    try:
        if template_manager is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Template manager not initialized"
            )

        # Validate template name format
        if not template_manager.validate_template_name(data.name):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Template name must be UPPERCASE_SNAKE_CASE (e.g., NEW_TEMPLATE_NAME)"
            )

        # Extract template data (exclude name field)
        template_data = data.model_dump(exclude={"name"})

        # Create template
        template_manager.create_template(data.name, template_data)

        logger.info(f"New template created by admin: {data.name}")

        return {
            "success": True,
            "message": f"Template '{data.name}' created successfully",
            "reloaded": True
        }

    except ValueError as e:
        # Template already exists or validation error
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating template: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Creation failed: {str(e)}"
        )


@app.delete("/admin/templates/{name}", tags=["Admin"])
async def delete_template(name: str, session: str = Depends(verify_admin_session)):
    """
    Delete a template.

    WARNING: This action cannot be undone. A backup is created automatically.
    """
    try:
        if template_manager is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Template manager not initialized"
            )

        # Delete template
        template_manager.delete_template(name)

        logger.info(f"Template deleted by admin: {name}")

        return {
            "success": True,
            "message": f"Template '{name}' deleted successfully",
            "reloaded": True
        }

    except ValueError as e:
        # Template not found
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting template {name}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Deletion failed: {str(e)}"
        )


@app.post("/admin/templates/reload", tags=["Admin"])
async def reload_templates_endpoint(session: str = Depends(verify_admin_session)):
    """
    Force reload all templates from disk.

    Useful if templates.json was modified externally.
    """
    try:
        from tools.template_tools import reload_templates

        templates = reload_templates()

        logger.info("Templates manually reloaded by admin")

        return {
            "success": True,
            "message": "Templates reloaded successfully",
            "count": len(templates)
        }

    except Exception as e:
        logger.error(f"Error reloading templates: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Reload failed: {str(e)}"
        )


@app.post("/admin/logout", tags=["Admin"])
async def admin_logout(response: Response, admin_session: Optional[str] = Cookie(None)):
    """
    Logout admin user and clear session.
    """
    if admin_session and admin_session in admin_sessions:
        admin_sessions.discard(admin_session)  # Remove from set

    # Clear cookie with same settings as login
    response.delete_cookie(
        key="admin_session",
        path="/"
    )

    return {"success": True, "message": "Logged out successfully"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "8009")),
        reload=os.getenv("API_RELOAD", "false").lower() == "true"
    )
