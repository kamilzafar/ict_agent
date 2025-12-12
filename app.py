"""FastAPI application for the intelligent chat agent."""
import os
import logging
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import FastAPI, HTTPException, status, Request, Header, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv
from typing import Optional, List, Dict, Any

from core.agent import IntelligentChatAgent

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global agent instance
agent: Optional[IntelligentChatAgent] = None

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
    global agent
    
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
    
    try:
        agent = IntelligentChatAgent(
            model_name=os.getenv("MODEL_NAME", "gpt-4o"),  # Default to gpt-4o for large context
            temperature=float(os.getenv("TEMPERATURE", "0.7")),
            memory_db_path=os.getenv("MEMORY_DB_PATH", "./memory_db"),
            summarize_interval=int(os.getenv("SUMMARIZE_INTERVAL", "10"))
        )
        logger.info("Agent initialized successfully")
        logger.info(f"Model: {os.getenv('MODEL_NAME', 'gpt-4o')}")
        logger.info(f"Memory DB: {os.getenv('MEMORY_DB_PATH', './memory_db')}")
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        raise
    except Exception as e:
        logger.error(f"Error initializing agent: {e}", exc_info=True)
        raise RuntimeError(f"Failed to initialize agent: {str(e)}") from e
    
    yield
    
    # Shutdown: Cleanup if needed
    print("Shutting down...")


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


@app.get("/health", tags=["Health"], response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        agent_initialized=agent is not None,
        memory_db_path=os.getenv("MEMORY_DB_PATH", "./memory_db")
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
                "summary": conv_data.get("summary")
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


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "8009")),
        reload=os.getenv("API_RELOAD", "false").lower() == "true"
    )

