"""FastAPI application for the intelligent chat agent."""
import os
import logging
import asyncio
import sys
import time
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path

# Import fcntl only on Unix systems
if sys.platform != "win32":
    import fcntl

from fastapi import FastAPI, HTTPException, status, Request, Header, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
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
            sheets_cache_service = GoogleSheetsCacheService(
                redis_host=os.getenv("REDIS_HOST", "localhost"),
                redis_port=int(os.getenv("REDIS_PORT", "6379")),
                redis_password=os.getenv("REDIS_PASSWORD"),
                redis_db=int(os.getenv("REDIS_DB", "0")),
                chroma_db_path=os.getenv("CHROMA_DB_PATH", "./sheets_index_db")
            )
            
            # Pre-load all sheets on startup (only from one worker to avoid DB locking)
            # Use file lock to ensure only one worker pre-loads
            lock_file_path = Path(os.getenv("CHROMA_DB_PATH", "./sheets_index_db")) / ".preload.lock"
            lock_file_path.parent.mkdir(parents=True, exist_ok=True)
            
            should_preload = False
            lock_file = None
            
            try:
                # Try to acquire lock (non-blocking)
                lock_file = open(lock_file_path, 'w')
                try:
                    # Try to acquire exclusive lock (non-blocking)
                    if sys.platform != "win32":
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    else:
                        # Windows: use msvcrt for file locking
                        import msvcrt
                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    
                    should_preload = True
                    logger.info("Acquired pre-load lock - this worker will pre-load sheets")
                except (IOError, OSError, BlockingIOError):
                    # Another worker has the lock
                    logger.info("Another worker is pre-loading sheets - skipping pre-load")
                    should_preload = False
            except ImportError:
                # fcntl not available (Windows), use simple file existence check
                if lock_file_path.exists():
                    logger.info("Pre-load lock file exists - another worker is pre-loading sheets")
                    should_preload = False
                else:
                    # Create lock file
                    try:
                        lock_file_path.write_text(str(os.getpid()))
                        should_preload = True
                        logger.info("Created pre-load lock - this worker will pre-load sheets")
                    except Exception as e:
                        logger.warning(f"Could not create pre-load lock: {e}. Skipping pre-load.")
                        should_preload = False
            except Exception as e:
                logger.warning(f"Could not acquire pre-load lock: {e}. Skipping pre-load to avoid conflicts.")
                should_preload = False
            
            if should_preload:
                logger.info("Pre-loading Google Sheets data...")
                try:
                    sheets_cache_service.preload_all_sheets()
                    logger.info("Google Sheets cache initialized successfully")
                except Exception as e:
                    logger.error(f"Error pre-loading sheets: {e}")
                    logger.warning("Continuing without pre-loaded sheets - will retry on first webhook")
                finally:
                    # Release lock
                    if lock_file:
                        try:
                            if sys.platform != "win32":
                                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                            else:
                                try:
                                    import msvcrt
                                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                                except ImportError:
                                    pass
                            lock_file.close()
                        except Exception as e:
                            logger.warning(f"Error releasing lock: {e}")
                    # Remove lock file
                    try:
                        if lock_file_path.exists():
                            lock_file_path.unlink()
                    except Exception as e:
                        logger.warning(f"Error removing lock file: {e}")
            else:
                # Wait a bit for the other worker to finish pre-loading
                logger.info("Waiting for pre-load to complete...")
                max_wait = 60  # Wait up to 60 seconds
                wait_interval = 2
                waited = 0
                while waited < max_wait:
                    if not lock_file_path.exists():
                        logger.info("Pre-load completed by another worker")
                        break
                    time.sleep(wait_interval)
                    waited += wait_interval
                else:
                    logger.warning("Pre-load lock still present after waiting - continuing anyway")
                if lock_file:
                    lock_file.close()
            
            # Start fallback polling task
            polling_task = asyncio.create_task(fallback_polling_task(sheets_cache_service))
            logger.info("Background polling task started")
        else:
            logger.warning(
                "Google Sheets not configured - skipping cache service initialization. "
                "Configure either GOOGLE_SHEETS_CREDENTIALS_PATH (service account) or "
                "GOOGLE_SHEETS_CLIENT_ID/CLIENT_SECRET/REFRESH_TOKEN (OAuth2)"
            )
    except Exception as e:
        logger.error(f"Error initializing Google Sheets cache service: {e}", exc_info=True)
        logger.warning("Continuing without Google Sheets cache - agent will work but without sheet data")
        sheets_cache_service = None  # Ensure it's set to None on error
    
    try:
        agent = IntelligentChatAgent(
            model_name=os.getenv("MODEL_NAME", "gpt-4.1-mini"),  # Default to gpt-4.1-mini for 128k context window
            temperature=float(os.getenv("TEMPERATURE", "0.7")),
            memory_db_path=os.getenv("MEMORY_DB_PATH", "./memory_db"),
            summarize_interval=int(os.getenv("SUMMARIZE_INTERVAL", "10")),
            sheets_cache_service=sheets_cache_service
        )
        logger.info("Agent initialized successfully")
        logger.info(f"Model: {os.getenv('MODEL_NAME', 'gpt-4.1-mini')}")
        logger.info(f"Memory DB: {os.getenv('MEMORY_DB_PATH', './memory_db')}")
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        raise
    except Exception as e:
        logger.error(f"Error initializing agent: {e}", exc_info=True)
        raise RuntimeError(f"Failed to initialize agent: {str(e)}") from e
    
    yield
    
    # Shutdown: Cleanup
    if polling_task:
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass
    logger.info("Shutting down...")


# Create FastAPI app
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "8009")),
        reload=os.getenv("API_RELOAD", "false").lower() == "true"
    )
