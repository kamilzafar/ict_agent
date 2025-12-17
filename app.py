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
from core.sheets_cache import GoogleSheetsCacheService
from core.background_tasks import fallback_polling_task

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

# Global cache service instance
sheets_cache_service: Optional[GoogleSheetsCacheService] = None

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
    global agent, sheets_cache_service
    
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
    
    # Initialize Google Sheets cache service (if configured)
    polling_task = None
    try:
        # Check if Google Sheets is configured (either service account or OAuth2)
        has_service_account = bool(os.getenv("GOOGLE_SHEETS_CREDENTIALS_PATH"))
        has_oauth2 = bool(
            os.getenv("GOOGLE_SHEETS_CLIENT_ID") and 
            os.getenv("GOOGLE_SHEETS_CLIENT_SECRET") and 
            os.getenv("GOOGLE_SHEETS_REFRESH_TOKEN")
        )
        has_spreadsheet_id = bool(os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID"))
        
        if (has_service_account or has_oauth2) and has_spreadsheet_id:
            logger.info("Initializing Google Sheets cache service...")
            try:
                sheets_cache_service = GoogleSheetsCacheService(
                    redis_host=os.getenv("REDIS_HOST", "localhost"),
                    redis_port=int(os.getenv("REDIS_PORT", "6379")),
                    redis_password=os.getenv("REDIS_PASSWORD"),
                    redis_db=int(os.getenv("REDIS_DB", "0")),
                    chroma_db_path=os.getenv("CHROMA_DB_PATH", "/app/sheets_index_db")
                )
                
                # Pre-load all sheets on startup (only from one worker to avoid DB locking)
                # Use file lock to ensure only one worker pre-loads
                lock_file_path = Path(os.getenv("CHROMA_DB_PATH", "/app/sheets_index_db")) / ".preload.lock"
                lock_file_path.parent.mkdir(parents=True, exist_ok=True)
                
                should_preload = False
                lock_file = None
                
                if not lock_file_path.exists():
                    should_preload = True
                else:
                    with open(lock_file_path, "r") as f:
                        lock_file = f.read()
                        if lock_file.strip() == "1":
                            should_preload = False
                        else:
                            should_preload = True
                            
                if should_preload:
                    logger.info("Pre-loading sheets...")
                    with open(lock_file_path, "w") as f:
                        f.write("1")
                    try:
                        sheets_cache_service.preload_all_sheets()
                        logger.info("Sheets pre-loaded successfully")
                    except Exception as e:
                        logger.error(f"Error pre-loading sheets: {e}", exc_info=True)
                        # Don't raise - app can still work without pre-loaded sheets
                    finally:
                        if lock_file:
                            with open(lock_file_path, "w") as f:
                                f.write("0")
                        lock_file_path.unlink()
                else:
                    logger.info("Sheets already pre-loaded")
                    
                logger.info("✓ Google Sheets cache service initialized successfully")
            except Exception as sheets_error:
                # Google Sheets initialization failed - log warning but don't crash app
                logger.warning("=" * 70)
                logger.warning("⚠️  Google Sheets cache service initialization failed!")
                logger.warning(f"Error: {sheets_error}")
                logger.warning("The app will continue without Google Sheets caching.")
                logger.warning("")
                logger.warning("To fix Google Sheets authentication:")
                if has_oauth2:
                    logger.warning("  1. Verify OAuth2 credentials in .env:")
                    logger.warning("     - GOOGLE_SHEETS_CLIENT_ID")
                    logger.warning("     - GOOGLE_SHEETS_CLIENT_SECRET")
                    logger.warning("     - GOOGLE_SHEETS_REFRESH_TOKEN")
                    logger.warning("  2. Check that refresh token is valid (not expired/revoked)")
                    logger.warning("  3. Verify OAuth2 client exists in Google Cloud Console")
                else:
                    logger.warning("  1. Set GOOGLE_SHEETS_CREDENTIALS_PATH to service account JSON")
                    logger.warning("  2. Or configure OAuth2 credentials")
                logger.warning("  4. Verify GOOGLE_SHEETS_SPREADSHEET_ID is correct")
                logger.warning("  5. Restart the application after fixing credentials")
                logger.warning("=" * 70)
                sheets_cache_service = None  # Set to None so agent can still initialize
        else:
            logger.info("Google Sheets not configured - skipping cache service initialization")
            logger.info("To enable Google Sheets, set:")
            logger.info("  - GOOGLE_SHEETS_SPREADSHEET_ID")
            logger.info("  - Either GOOGLE_SHEETS_CREDENTIALS_PATH (service account)")
            logger.info("    Or GOOGLE_SHEETS_CLIENT_ID/CLIENT_SECRET/REFRESH_TOKEN (OAuth2)")
            sheets_cache_service = None
    except Exception as e:
        # Catch any unexpected errors and make Google Sheets optional
        logger.warning(f"Unexpected error during Google Sheets initialization: {e}", exc_info=True)
        logger.warning("Continuing without Google Sheets cache service")
        sheets_cache_service = None
    try:
        agent = IntelligentChatAgent(
            model_name=os.getenv("MODEL_NAME", "gpt-4.1-mini"),  # Default to gpt-4.1-mini for 128k context window
            temperature=float(os.getenv("TEMPERATURE", "0.7")),
            memory_db_path=os.getenv("MEMORY_DB_PATH", "/app/memory_db"),
            summarize_interval=int(os.getenv("SUMMARIZE_INTERVAL", "10")),
            sheets_cache_service=sheets_cache_service
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
    if polling_task:
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass
    logger.info("Shutting down...")


# ============================================================================
# Admin Session Management
# ============================================================================

# In-memory session storage
# For production with multiple workers, consider using Redis
admin_sessions: Dict[str, datetime] = {}  # session_id -> expiry_time
ADMIN_SESSION_TIMEOUT = int(os.getenv("ADMIN_SESSION_TIMEOUT", "3600"))  # 1 hour default


def create_session() -> str:
    """Create new admin session with timeout."""
    session_id = secrets.token_urlsafe(32)
    admin_sessions[session_id] = datetime.now() + timedelta(seconds=ADMIN_SESSION_TIMEOUT)
    return session_id


def validate_session(session_id: str) -> bool:
    """Validate admin session and extend if valid."""
    if session_id not in admin_sessions:
        return False

    if datetime.now() > admin_sessions[session_id]:
        # Session expired - remove it
        del admin_sessions[session_id]
        return False

    # Valid session - extend the expiry (sliding expiration)
    admin_sessions[session_id] = datetime.now() + timedelta(seconds=ADMIN_SESSION_TIMEOUT)
    return True


def verify_admin_session(admin_session: Optional[str] = Cookie(None)):
    """Dependency for admin endpoints - validates session cookie."""
    if not admin_session or not validate_session(admin_session):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session. Please login again."
        )
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
    sheets_cache_initialized: bool = False
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


@app.get("/debug/sheets", tags=["Debug"])
async def debug_sheets():
    """Debug endpoint to test Google Sheets connection and list available sheets."""
    if not sheets_cache_service:
        return {
            "error": "Google Sheets cache service not initialized",
            "spreadsheet_id": os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "Not set"),
            "configured_sheets": os.getenv("GOOGLE_SHEETS_SHEET_NAMES", "Not set")
        }
    
    try:
        available_sheets = sheets_cache_service.list_available_sheets()
        return {
            "status": "success",
            "spreadsheet_id": sheets_cache_service.spreadsheet_id,
            "configured_sheets": sheets_cache_service.sheet_names,
            "available_sheets": available_sheets,
            "sheets_match": all(s in available_sheets for s in sheets_cache_service.sheet_names),
            "missing_sheets": [s for s in sheets_cache_service.sheet_names if s not in available_sheets]
        }
    except Exception as e:
        return {
            "status": "error",
            "spreadsheet_id": sheets_cache_service.spreadsheet_id,
            "configured_sheets": sheets_cache_service.sheet_names,
            "error": str(e),
            "error_type": type(e).__name__
        }


@app.get("/health", tags=["Health"], response_model=HealthResponse)
async def health_check():
    """Health check endpoint with comprehensive status."""
    redis_connected = False
    if sheets_cache_service and sheets_cache_service.redis_client:
        try:
            sheets_cache_service.redis_client.ping()
            redis_connected = True
        except Exception:
            redis_connected = False
    
    return HealthResponse(
        status="healthy" if agent is not None else "degraded",
        agent_initialized=agent is not None,
        memory_db_path=os.getenv("MEMORY_DB_PATH", "./memory_db"),
        sheets_cache_initialized=sheets_cache_service is not None,
        redis_connected=redis_connected,
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


# Webhook Models
class WebhookPayload(BaseModel):
    """Payload model for Google Sheets webhook."""
    spreadsheet_id: str = Field(..., description="Google Sheets spreadsheet ID")
    sheet_name: str = Field(..., description="Name of the sheet that was updated")
    action: str = Field(default="updated", description="Action type (updated, form_submitted, manual_sync)")
    timestamp: Optional[str] = Field(None, description="Timestamp of the update")


@app.post("/webhooks/google-sheets-update", tags=["Webhooks"])
async def google_sheets_webhook(
    payload: WebhookPayload,
    request: Request,
    x_webhook_secret: Optional[str] = Header(None, alias="X-Webhook-Secret")
):
    """Webhook endpoint for real-time Google Sheets updates.
    
    This is the PRIMARY sync mechanism - updates happen instantly when
    sheets are modified via Google Apps Script trigger.
    
    Args:
        payload: Webhook payload with sheet information
        request: FastAPI request object
        x_webhook_secret: Webhook secret from header
    
    Returns:
        Status of the update operation
    """
    # Check if webhook is enabled
    webhook_enabled = os.getenv("SHEETS_WEBHOOK_ENABLED", "true").lower() == "true"
    if not webhook_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook endpoint is disabled"
        )
    
    # Verify webhook secret
    expected_secret = os.getenv("SHEETS_WEBHOOK_SECRET")
    if not expected_secret:
        logger.error("SHEETS_WEBHOOK_SECRET not configured")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook not configured"
        )
    
    if not x_webhook_secret or x_webhook_secret != expected_secret:
        logger.warning(f"Invalid webhook secret attempt from {request.client.host if request.client else 'unknown'}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized"
        )
    
    # Check if cache service is initialized
    if sheets_cache_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Sheets cache service not initialized"
        )
    
    try:
        logger.info(f"Webhook received: {payload.sheet_name} updated (action: {payload.action})")
        
        # Immediately sync the sheet
        updated = sheets_cache_service.sync_sheet(payload.sheet_name)
        
        if updated:
            logger.info(f"Successfully updated cache for {payload.sheet_name}")
            return {
                "status": "success",
                "sheet": payload.sheet_name,
                "updated": True,
                "message": "Cache refreshed successfully"
            }
        else:
            logger.info(f"No changes detected for {payload.sheet_name}")
            return {
                "status": "success",
                "sheet": payload.sheet_name,
                "updated": False,
                "message": "No changes detected"
            }
    
    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        # Return 200 to prevent retries for permanent errors
        # But log the error for investigation
        return {
            "status": "error",
            "message": str(e),
            "sheet": payload.sheet_name
        }


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

    # Set secure cookie
    response.set_cookie(
        key="admin_session",
        value=session_id,
        httponly=True,
        samesite="strict",
        max_age=ADMIN_SESSION_TIMEOUT
    )

    logger.info(f"Admin login successful: {username}")

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
        del admin_sessions[admin_session]

    # Clear cookie
    response.delete_cookie("admin_session")

    return {"success": True, "message": "Logged out successfully"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "8009")),
        reload=os.getenv("API_RELOAD", "false").lower() == "true"
    )
