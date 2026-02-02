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

from dotenv import load_dotenv

# Load environment variables FIRST (before Sentry init)
load_dotenv()

# ============================================================================
# Sentry Error Tracking
# ============================================================================
# Initialize Sentry BEFORE FastAPI app creation for proper error capture
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

# Get Sentry DSN from environment (optional - if not set, Sentry is disabled)
SENTRY_DSN = os.getenv("SENTRY_DSN")

if SENTRY_DSN:
    # Get sample rate from environment
    _sentry_sample_rate = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"))

    def _sentry_traces_sampler(sampling_context: dict) -> float:
        """
        Custom traces sampler to filter out noisy endpoints.
        Docs: https://docs.sentry.io/platforms/python/configuration/sampling/
        """
        asgi_scope = sampling_context.get("asgi_scope", {})
        path = asgi_scope.get("path", "")

        # Don't trace health checks, docs, and static endpoints
        if path in ["/health", "/", "/docs", "/redoc", "/openapi.json"]:
            return 0.0

        return _sentry_sample_rate

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        # Environment (production, staging, development)
        environment=os.getenv("ENVIRONMENT", "development"),
        # Release version for tracking deployments
        release=os.getenv("APP_VERSION", "1.0.0"),
        # Send PII data (IP addresses, user info, request headers)
        # Docs: https://docs.sentry.io/platforms/python/data-management/data-collected/
        send_default_pii=True,
        # Custom traces sampler (filters out health checks)
        # Note: When traces_sampler is set, traces_sample_rate is ignored
        traces_sampler=_sentry_traces_sampler,
        # Sample rate for profiling (0.0 to 1.0)
        profiles_sample_rate=float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.1")),
        # Integrations for FastAPI
        # Docs: https://docs.sentry.io/platforms/python/integrations/fastapi/
        integrations=[
            StarletteIntegration(
                transaction_style="endpoint",  # Use endpoint function names
                failed_request_status_codes={400, 403, *range(500, 599)},  # Capture these as errors
            ),
            FastApiIntegration(
                transaction_style="endpoint",
                failed_request_status_codes={400, 403, *range(500, 599)},
            ),
            LoggingIntegration(
                level=logging.INFO,  # Capture INFO+ as breadcrumbs
                event_level=logging.ERROR,  # Send ERROR+ as events
            ),
        ],
        # Attach stack traces to log messages
        attach_stacktrace=True,
        # Include local variables in stack traces (helpful for debugging)
        include_local_variables=True,
        # Maximum breadcrumbs to keep
        max_breadcrumbs=50,
    )

from fastapi import FastAPI, HTTPException, status, Request, Header, Depends, Security, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from fastapi.exceptions import RequestValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field, field_validator
import json
import re

from core.agent import IntelligentChatAgent
from core.supabase_service import SupabaseService

# Configure logging with production-ready settings
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
is_production = os.getenv("ENVIRONMENT", "development").lower() == "production"

# Production logging format (more concise)
if is_production:
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
else:
    log_format = "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"

logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format=log_format,
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
    force=True  # Override any existing configuration
)
logger = logging.getLogger(__name__)

# Set log levels for noisy libraries in production
if is_production:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)

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
            recursion_limit=int(os.getenv("RECURSION_LIMIT", "50")),
            supabase_service=supabase_service
        )
        logger.info("✓ Agent initialized successfully")
        logger.info(f"  Model: {os.getenv('MODEL_NAME', 'gpt-4.1-mini')}")
        logger.info(f"  Memory DB: {os.getenv('MEMORY_DB_PATH', '/app/memory_db')}")
        logger.info(f"  Supabase: {'✓ Enabled' if supabase_service else '✗ Disabled'}")
        logger.info(f"  Sentry: {'✓ Enabled' if SENTRY_DSN else '✗ Disabled'}")

        # Log tool availability
        sheets_configured = bool(os.getenv("GOOGLE_SHEETS_CREDENTIALS_PATH") and os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID"))
        logger.info(f"  Google Sheets: {'✓ Configured' if sheets_configured else '✗ Not configured'}")
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        raise
    except Exception as e:
        logger.error(f"Error initializing agent: {e}", exc_info=True)
        raise RuntimeError(f"Failed to initialize agent: {str(e)}") from e

    yield
    
    # Shutdown: Cleanup
    logger.info("Shutting down...")


# ============================================================================
# Create FastAPI app
# ============================================================================
# root_path is used when behind a proxy (e.g., nginx) with subpath
root_path = os.getenv("ROOT_PATH", "")
app = FastAPI(
    title="Intelligent Chat Agent API",
    description="Production-ready API for interacting with an AI agent with long-term memory and vector database search. Supports multilingual content (Urdu, English, etc.) with UTF-8 encoding.",
    version="1.0.0",
    lifespan=lifespan,
    root_path=root_path,  # For nginx proxy with subpath
    docs_url="/docs",  # Always enable docs
    redoc_url="/redoc",  # Always enable redoc
    default_response_class=JSONResponse,  # Ensure UTF-8 JSON responses
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

# Middleware to fix JSON formatting issues (especially trailing quotes in multilingual content)
@app.middleware("http")
async def fix_json_middleware(request: Request, call_next):
    """Fix common JSON formatting issues, especially trailing quotes in multilingual content."""
    if request.method == "POST" and request.url.path == "/chat":
        try:
            body_bytes = await request.body()
            if body_bytes:
                try:
                    body_str = body_bytes.decode('utf-8')
                    
                    # Try to parse JSON first
                    try:
                        json.loads(body_str)
                        # JSON is valid, proceed normally
                    except json.JSONDecodeError as json_err:
                        # JSON is invalid, try to fix trailing quotes issue
                        # Pattern: "message": "text"" -> "message": "text"
                        # This fixes the specific issue: trailing "" before comma
                        logger.warning(f"Invalid JSON detected, attempting to fix: {json_err.msg} at position {json_err.pos}")
                        fixed_body = body_str
                        
                        # Fix trailing double quotes: "" before comma, newline, or closing brace
                        # This handles: "message": "text"" -> "message": "text"
                        # Pattern matches: "" followed by optional whitespace and comma/newline/brace
                        fixed_body = re.sub(r'("")(\s*[,\n}])', r'\2', fixed_body)
                        
                        # Also handle cases where quotes might be escaped differently
                        # Fix: \"\" before comma/newline/brace
                        fixed_body = re.sub(r'(\\"\\")(\s*[,\n}])', r'\2', fixed_body)
                        
                        # Try parsing again
                        try:
                            json.loads(fixed_body)
                            logger.info("Fixed JSON formatting issue: removed trailing quotes")
                            # Reconstruct request with fixed body
                            async def receive():
                                return {"type": "http.request", "body": fixed_body.encode('utf-8')}
                            request._receive = receive
                        except json.JSONDecodeError:
                            # Still invalid, proceed with original body (exception handler will catch it)
                            async def receive():
                                return {"type": "http.request", "body": body_bytes}
                            request._receive = receive
                except UnicodeDecodeError:
                    # Encoding issue, proceed with original body
                    async def receive():
                        return {"type": "http.request", "body": body_bytes}
                    request._receive = receive
        except Exception as e:
            logger.error(f"Error in JSON fix middleware: {e}")
    
    response = await call_next(request)
    return response

# Exception handler for JSON decode errors and validation errors
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle JSON decode errors and request validation errors."""
    # Try to get request body for better error messages
    body = None
    try:
        body_bytes = await request.body()
        if body_bytes:
            try:
                body = body_bytes.decode('utf-8')
                logger.error(f"JSON validation error - Body length: {len(body)}")
                logger.error(f"Body preview: {body[:300]}")
            except UnicodeDecodeError:
                logger.error("Unicode decode error in request body")
    except Exception:
        pass
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": exc.errors(),
            "message": "Invalid JSON format. Please ensure your request body is valid JSON with proper UTF-8 encoding for multilingual content."
        },
        media_type="application/json; charset=utf-8"
    )


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle unhandled exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)

    # Capture exception in Sentry with request context
    if SENTRY_DSN:
        with sentry_sdk.push_scope() as scope:
            scope.set_tag("endpoint", request.url.path)
            scope.set_tag("method", request.method)
            scope.set_extra("url", str(request.url))
            scope.set_extra("headers", dict(request.headers))
            sentry_sdk.capture_exception(exc)

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred"},
        media_type="application/json; charset=utf-8"
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
    supabase_connected: bool = False
    sentry_enabled: bool = False
    version: str = "1.0.0"


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


@app.get("/debug/sentry", tags=["Debug"])
async def debug_sentry():
    """Debug endpoint to test Sentry error reporting.

    Triggers a test exception to verify Sentry is working.
    Only available in non-production environments.
    """
    if is_production:
        return {
            "status": "skipped",
            "message": "Sentry test endpoint disabled in production"
        }

    if not SENTRY_DSN:
        return {
            "status": "disabled",
            "message": "Sentry is not configured. Set SENTRY_DSN in environment."
        }

    try:
        # Send a test message to Sentry
        sentry_sdk.capture_message("Sentry test message from ICT Agent", level="info")

        # Trigger a test exception (caught and reported)
        with sentry_sdk.push_scope() as scope:
            scope.set_tag("test", "true")
            scope.set_extra("purpose", "Verify Sentry integration")
            try:
                raise ValueError("This is a test exception for Sentry")
            except ValueError as e:
                sentry_sdk.capture_exception(e)

        return {
            "status": "success",
            "message": "Test error sent to Sentry. Check your Sentry dashboard.",
            "dsn_configured": True,
            "environment": os.getenv("ENVIRONMENT", "development")
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to send test to Sentry: {str(e)}"
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
            "cache_enabled": False,
            "note": "Caching disabled - all queries go directly to database"
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
    """Clear cache endpoint - kept for API compatibility.
    
    Note: Caching is disabled - all queries go directly to the database.
    This endpoint is a no-op but kept for backward compatibility.
    
    Args:
        table: Optional table name (ignored - no cache to clear)
    """
    if not supabase_service:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase service not initialized"
        )
    
    supabase_service.clear_cache(table)
    return {
        "status": "success",
        "message": "Cache clear requested (caching is disabled - all queries are direct DB calls)",
        "note": "No cache exists - all queries already go directly to Supabase database"
    }


@app.get("/health", tags=["Health"], response_model=HealthResponse)
async def health_check():
    """Health check endpoint with comprehensive production status."""
    supabase_connected = False
    if supabase_service:
        try:
            # Test connection with a simple query
            supabase_service.get_company_info()
            supabase_connected = True
        except Exception:
            supabase_connected = False
    
    # Check if agent has tools available
    tools_available = False
    checkpointer_ok = False
    memory_db_ok = False
    
    if agent:
        try:
            tools_available = len(agent.all_tools) > 0
            # Check checkpointer status
            checkpointer_ok = hasattr(agent, 'checkpointer') and agent.checkpointer is not None
            # Check memory database accessibility
            memory_db_path = os.getenv("MEMORY_DB_PATH", "/app/memory_db")
            memory_db_ok = os.path.exists(memory_db_path) and os.access(memory_db_path, os.W_OK)
        except Exception:
            pass
    
    # Determine overall health status
    if agent is not None and tools_available and checkpointer_ok and memory_db_ok:
        status = "healthy"
    elif agent is not None:
        status = "degraded"
    else:
        status = "unhealthy"
    
    return HealthResponse(
        status=status,
        agent_initialized=agent is not None,
        memory_db_path=os.getenv("MEMORY_DB_PATH", "/app/memory_db"),
        supabase_connected=supabase_connected,
        sentry_enabled=bool(SENTRY_DSN),
        version="1.0.0"
    )


@app.post("/chat", tags=["Chat"], response_model=ChatResponse, dependencies=[Depends(verify_api_key)])
async def chat(request: ChatRequest):
    """Send a message to the agent and get a response.

    Supports multilingual content (Urdu, English, etc.) with UTF-8 encoding.

    Args:
        request: Chat request containing message and optional conversation_id

    Returns:
        ChatResponse with agent's response and metadata (UTF-8 encoded)

    Raises:
        HTTPException: If agent is not initialized or error occurs
    """
    if agent is None:
        logger.error("Agent not initialized")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent is not initialized"
        )

    # Set Sentry user context for better error tracking
    if SENTRY_DSN:
        sentry_sdk.set_user({
            "id": request.conversation_id or "anonymous",
            "conversation_id": request.conversation_id,
        })
        sentry_sdk.set_tag("conversation_id", request.conversation_id or "new")

    try:
        logger.info(f"Processing chat request - conversation_id: {request.conversation_id}")
        logger.debug(f"Message preview: {request.message[:100]}...")
        
        # Process the message (agent handles multilingual content automatically)
        result = agent.chat(
            user_input=request.message,
            conversation_id=request.conversation_id
        )
        
        logger.info(f"Chat request completed - conversation_id: {result['conversation_id']}, turn: {result['turn_count']}")
        
        # Return response with explicit UTF-8 encoding
        response_data = ChatResponse(
            response=result["response"],
            conversation_id=result["conversation_id"],
            turn_count=result["turn_count"],
            context_used=result.get("context_used", []),
            stage=result.get("stage", "NEW"),
            lead_data=result.get("lead_data", {}),
            timestamp=datetime.now().isoformat()
        )
        
        return JSONResponse(
            content=response_data.model_dump(),
            media_type="application/json; charset=utf-8"
        )
    
    except ValueError as e:
        logger.warning(f"Validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except RuntimeError as e:
        # This is the error from agent.chat() - EXPOSE THE ACTUAL ERROR
        error_msg = str(e)
        logger.error(f"Agent runtime error: {error_msg}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent error: {error_msg}"
        )
    except Exception as e:
        # Log full error with stack trace and EXPOSE IT
        error_msg = str(e)
        logger.error(f"Unexpected error processing message: {error_msg}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing message: {error_msg}"
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "8009")),
        reload=os.getenv("API_RELOAD", "false").lower() == "true"
    )
