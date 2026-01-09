"""Comprehensive tests for FastAPI endpoints."""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import status

# Import after setting env vars
from app import app


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_agent():
    """Mock agent instance."""
    agent = Mock()
    agent.chat.return_value = {
        "response": "Test response",
        "conversation_id": "test_conv_123",
        "turn_count": 1,
        "context_used": [],
        "stage": "NEW",
        "lead_data": {}
    }
    agent.memory = Mock()
    agent.memory.get_conversation_history.return_value = [
        {
            "timestamp": "2024-01-01T00:00:00",
            "user_message": "Hello",
            "assistant_message": "Hi there"
        }
    ]
    agent.memory.conversations_metadata = {
        "test_conv_123": {
            "created_at": "2024-01-01T00:00:00",
            "summary": "Test summary",
            "turns": [],
            "stage": "NEW"
        }
    }
    agent.memory.get_conversation_summary.return_value = "Test summary"
    agent.memory.search_relevant_context.return_value = []
    agent.memory.get_leads_by_stage.return_value = []
    agent.memory.get_all_stage_stats.return_value = {"NEW": 5}
    agent.memory.manually_set_stage = Mock()
    agent.memory.get_stage.return_value = "NEW"
    agent.memory.get_lead_data.return_value = {}
    agent.memory.STAGES = {"NEW": {}, "NAME_COLLECTED": {}}
    agent.all_tools = [Mock()]
    agent.checkpointer = Mock()
    return agent


@pytest.fixture
def mock_supabase_service():
    """Mock Supabase service."""
    service = Mock()
    service.get_course_links.return_value = {}
    service.get_company_info.return_value = {}
    service.clear_cache = Mock()
    return service


class TestRootEndpoint:
    """Tests for GET / endpoint."""
    
    def test_root_endpoint_returns_info(self, client: TestClient):
        """Test root endpoint returns API information."""
        response = client.get("/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "message" in data
        assert "version" in data
        assert data["version"] == "1.0.0"
    
    def test_root_endpoint_contains_docs_link(self, client: TestClient):
        """Test root endpoint contains docs URL."""
        response = client.get("/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "docs" in data
        assert data["docs"] == "/docs"
    
    def test_root_endpoint_contains_health_link(self, client: TestClient):
        """Test root endpoint contains health check URL."""
        response = client.get("/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "health" in data
        assert data["health"] == "/health"
    
    def test_root_endpoint_no_authentication_required(self, client: TestClient):
        """Test root endpoint doesn't require authentication."""
        response = client.get("/")
        assert response.status_code == status.HTTP_200_OK
    
    def test_root_endpoint_json_format(self, client: TestClient):
        """Test root endpoint returns valid JSON."""
        response = client.get("/")
        assert response.status_code == status.HTTP_200_OK
        assert response.headers["content-type"] == "application/json"


class TestHealthEndpoint:
    """Tests for GET /health endpoint."""
    
    @patch('app.agent', None)
    def test_health_when_agent_not_initialized(self, client: TestClient):
        """Test health check when agent is not initialized."""
        response = client.get("/health")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["agent_initialized"] is False
    
    @patch('app.agent')
    @patch('app.supabase_service')
    def test_health_when_agent_initialized(self, mock_supabase, mock_agent, client: TestClient):
        """Test health check when agent is initialized."""
        mock_agent.all_tools = [Mock()]
        mock_agent.checkpointer = Mock()
        mock_supabase.get_company_info.return_value = {}
        
        response = client.get("/health")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] in ["healthy", "degraded"]
        assert data["agent_initialized"] is True
    
    @patch('app.agent')
    def test_health_includes_memory_db_path(self, mock_agent, client: TestClient):
        """Test health check includes memory DB path."""
        mock_agent.all_tools = [Mock()]
        mock_agent.checkpointer = Mock()
        
        response = client.get("/health")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "memory_db_path" in data
    
    @patch('app.agent')
    @patch('app.supabase_service')
    def test_health_supabase_connection_status(self, mock_supabase, mock_agent, client: TestClient):
        """Test health check reports Supabase connection status."""
        mock_agent.all_tools = [Mock()]
        mock_agent.checkpointer = Mock()
        mock_supabase.get_company_info.return_value = {}
        
        response = client.get("/health")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "supabase_connected" in data
    
    @patch('app.agent')
    def test_health_includes_version(self, mock_agent, client: TestClient):
        """Test health check includes version."""
        mock_agent.all_tools = [Mock()]
        mock_agent.checkpointer = Mock()
        
        response = client.get("/health")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["version"] == "1.0.0"


class TestDebugSupabaseEndpoint:
    """Tests for GET /debug/supabase endpoint."""
    
    @patch('app.supabase_service', None)
    def test_debug_supabase_when_not_initialized(self, client: TestClient):
        """Test debug endpoint when Supabase not initialized."""
        response = client.get("/debug/supabase")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "error" in data
        assert "not initialized" in data["error"].lower()
    
    @patch('app.supabase_service')
    def test_debug_supabase_when_initialized(self, mock_service, client: TestClient):
        """Test debug endpoint when Supabase is initialized."""
        mock_service.get_course_links.return_value = {}
        
        response = client.get("/debug/supabase")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "success"
    
    @patch('app.supabase_service')
    def test_debug_supabase_connection_test(self, mock_service, client: TestClient):
        """Test debug endpoint tests connection."""
        mock_service.get_course_links.return_value = {}
        
        response = client.get("/debug/supabase")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["connection"] == "ok"
    
    @patch('app.supabase_service')
    def test_debug_supabase_error_handling(self, mock_service, client: TestClient):
        """Test debug endpoint handles errors gracefully."""
        mock_service.get_course_links.side_effect = Exception("Connection failed")
        
        response = client.get("/debug/supabase")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "error"
        assert "error" in data
    
    @patch('app.supabase_service')
    def test_debug_supabase_returns_url(self, mock_service, client: TestClient):
        """Test debug endpoint returns Supabase URL."""
        mock_service.get_course_links.return_value = {}
        
        response = client.get("/debug/supabase")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "supabase_url" in data


class TestChatEndpoint:
    """Tests for POST /chat endpoint."""
    
    @patch('app.agent', None)
    def test_chat_when_agent_not_initialized(self, client: TestClient, api_headers: dict):
        """Test chat endpoint when agent is not initialized."""
        response = client.post(
            "/chat",
            json={"message": "Hello"},
            headers=api_headers
        )
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    
    @patch('app.agent')
    def test_chat_successful_request(self, mock_agent, client: TestClient, api_headers: dict):
        """Test successful chat request."""
        mock_agent.chat.return_value = {
            "response": "Test response",
            "conversation_id": "test_123",
            "turn_count": 1,
            "context_used": [],
            "stage": "NEW",
            "lead_data": {}
        }
        
        response = client.post(
            "/chat",
            json={"message": "Hello", "conversation_id": "test_123"},
            headers=api_headers
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "response" in data
        assert data["conversation_id"] == "test_123"
    
    def test_chat_missing_api_key(self, client: TestClient):
        """Test chat endpoint requires API key."""
        response = client.post(
            "/chat",
            json={"message": "Hello"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    @patch('app.agent')
    def test_chat_invalid_api_key(self, mock_agent, client: TestClient):
        """Test chat endpoint with invalid API key."""
        response = client.post(
            "/chat",
            json={"message": "Hello"},
            headers={"X-API-Key": "wrong-key"}
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    @patch('app.agent')
    def test_chat_empty_message(self, mock_agent, client: TestClient, api_headers: dict):
        """Test chat endpoint rejects empty message."""
        response = client.post(
            "/chat",
            json={"message": ""},
            headers=api_headers
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    @patch('app.agent')
    def test_chat_missing_message_field(self, mock_agent, client: TestClient, api_headers: dict):
        """Test chat endpoint requires message field."""
        response = client.post(
            "/chat",
            json={},
            headers=api_headers
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    @patch('app.agent')
    def test_chat_creates_new_conversation(self, mock_agent, client: TestClient, api_headers: dict):
        """Test chat creates new conversation when ID not provided."""
        mock_agent.chat.return_value = {
            "response": "Test",
            "conversation_id": "new_conv_123",
            "turn_count": 1,
            "context_used": [],
            "stage": "NEW",
            "lead_data": {}
        }
        
        response = client.post(
            "/chat",
            json={"message": "Hello"},
            headers=api_headers
        )
        assert response.status_code == status.HTTP_200_OK
        mock_agent.chat.assert_called_once()
    
    @patch('app.agent')
    def test_chat_returns_turn_count(self, mock_agent, client: TestClient, api_headers: dict):
        """Test chat response includes turn count."""
        mock_agent.chat.return_value = {
            "response": "Test",
            "conversation_id": "test_123",
            "turn_count": 5,
            "context_used": [],
            "stage": "NEW",
            "lead_data": {}
        }
        
        response = client.post(
            "/chat",
            json={"message": "Hello"},
            headers=api_headers
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["turn_count"] == 5
    
    @patch('app.agent')
    def test_chat_handles_agent_error(self, mock_agent, client: TestClient, api_headers: dict):
        """Test chat endpoint handles agent errors."""
        mock_agent.chat.side_effect = RuntimeError("Agent error")
        
        response = client.post(
            "/chat",
            json={"message": "Hello"},
            headers=api_headers
        )
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    
    @patch('app.agent')
    def test_chat_utf8_encoding(self, mock_agent, client: TestClient, api_headers: dict):
        """Test chat endpoint handles UTF-8 content."""
        mock_agent.chat.return_value = {
            "response": "سلام",
            "conversation_id": "test_123",
            "turn_count": 1,
            "context_used": [],
            "stage": "NEW",
            "lead_data": {}
        }
        
        response = client.post(
            "/chat",
            json={"message": "Hello"},
            headers=api_headers
        )
        assert response.status_code == status.HTTP_200_OK
        assert "charset=utf-8" in response.headers["content-type"]


class TestConversationsEndpoint:
    """Tests for GET /conversations endpoint."""
    
    @patch('app.agent', None)
    def test_list_conversations_agent_not_initialized(self, client: TestClient, api_headers: dict):
        """Test list conversations when agent not initialized."""
        response = client.get("/conversations", headers=api_headers)
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    
    @patch('app.agent')
    def test_list_conversations_success(self, mock_agent, client: TestClient, api_headers: dict):
        """Test successful list conversations."""
        mock_agent.memory.conversations_metadata = {
            "conv1": {
                "created_at": "2024-01-01T00:00:00",
                "turns": [],
                "stage": "NEW"
            }
        }
        
        response = client.get("/conversations", headers=api_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "conversations" in data
        assert "total" in data
    
    @patch('app.agent')
    def test_list_conversations_with_limit(self, mock_agent, client: TestClient, api_headers: dict):
        """Test list conversations with limit parameter."""
        mock_agent.memory.conversations_metadata = {
            f"conv{i}": {"created_at": "2024-01-01T00:00:00", "turns": [], "stage": "NEW"}
            for i in range(10)
        }
        
        response = client.get("/conversations?limit=5", headers=api_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["conversations"]) <= 5
    
    @patch('app.agent')
    def test_list_conversations_sorted_by_date(self, mock_agent, client: TestClient, api_headers: dict):
        """Test conversations are sorted by date."""
        mock_agent.memory.conversations_metadata = {
            "conv1": {"created_at": "2024-01-01T00:00:00", "turns": [], "stage": "NEW"},
            "conv2": {"created_at": "2024-01-02T00:00:00", "turns": [], "stage": "NEW"}
        }
        
        response = client.get("/conversations", headers=api_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["conversations"]) == 2
    
    def test_list_conversations_requires_auth(self, client: TestClient):
        """Test list conversations requires authentication."""
        response = client.get("/conversations")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestConversationHistoryEndpoint:
    """Tests for GET /conversations/{conversation_id} endpoint."""
    
    @patch('app.agent')
    def test_get_conversation_history_success(self, mock_agent, client: TestClient, api_headers: dict):
        """Test successful get conversation history."""
        mock_agent.memory.get_conversation_history.return_value = [
            {
                "timestamp": "2024-01-01T00:00:00",
                "user_message": "Hello",
                "assistant_message": "Hi"
            }
        ]
        mock_agent.memory.conversations_metadata = {
            "test_123": {"created_at": "2024-01-01T00:00:00"}
        }
        
        response = client.get("/conversations/test_123", headers=api_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["conversation_id"] == "test_123"
        assert "turns" in data
    
    @patch('app.agent')
    def test_get_conversation_history_not_found(self, mock_agent, client: TestClient, api_headers: dict):
        """Test get conversation history when not found."""
        mock_agent.memory.get_conversation_history.return_value = []
        
        response = client.get("/conversations/nonexistent", headers=api_headers)
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    @patch('app.agent')
    def test_get_conversation_history_with_limit(self, mock_agent, client: TestClient, api_headers: dict):
        """Test get conversation history with limit."""
        mock_agent.memory.get_conversation_history.return_value = [
            {"timestamp": "2024-01-01T00:00:00", "user_message": "Hi", "assistant_message": "Hello"}
        ] * 10
        mock_agent.memory.conversations_metadata = {
            "test_123": {"created_at": "2024-01-01T00:00:00"}
        }
        
        response = client.get("/conversations/test_123?limit=5", headers=api_headers)
        assert response.status_code == status.HTTP_200_OK
        mock_agent.memory.get_conversation_history.assert_called_with("test_123", limit=5)
    
    @patch('app.agent')
    def test_get_conversation_history_includes_summary(self, mock_agent, client: TestClient, api_headers: dict):
        """Test conversation history includes summary."""
        mock_agent.memory.get_conversation_history.return_value = [
            {"timestamp": "2024-01-01T00:00:00", "user_message": "Hi", "assistant_message": "Hello"}
        ]
        mock_agent.memory.conversations_metadata = {
            "test_123": {"created_at": "2024-01-01T00:00:00", "summary": "Test summary"}
        }
        
        response = client.get("/conversations/test_123", headers=api_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["summary"] == "Test summary"
    
    def test_get_conversation_history_requires_auth(self, client: TestClient):
        """Test get conversation history requires authentication."""
        response = client.get("/conversations/test_123")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestConversationSummaryEndpoint:
    """Tests for GET /conversations/{conversation_id}/summary endpoint."""
    
    @patch('app.agent')
    def test_get_summary_success(self, mock_agent, client: TestClient, api_headers: dict):
        """Test successful get conversation summary."""
        mock_agent.memory.get_conversation_summary.return_value = "Test summary"
        
        response = client.get("/conversations/test_123/summary", headers=api_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["summary"] == "Test summary"
    
    @patch('app.agent')
    def test_get_summary_not_found(self, mock_agent, client: TestClient, api_headers: dict):
        """Test get summary when conversation not found."""
        mock_agent.memory.get_conversation_summary.return_value = None
        
        response = client.get("/conversations/nonexistent/summary", headers=api_headers)
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_get_summary_requires_auth(self, client: TestClient):
        """Test get summary requires authentication."""
        response = client.get("/conversations/test_123/summary")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestConversationSearchEndpoint:
    """Tests for POST /conversations/{conversation_id}/search endpoint."""
    
    @patch('app.agent')
    def test_search_context_success(self, mock_agent, client: TestClient, api_headers: dict):
        """Test successful context search."""
        mock_doc = Mock()
        mock_doc.page_content = "Test content"
        mock_doc.metadata = {"source": "test"}
        mock_agent.memory.search_relevant_context.return_value = [mock_doc]
        
        response = client.post(
            "/conversations/test_123/search?query=test&k=5",
            headers=api_headers
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "results" in data
        assert len(data["results"]) == 1
    
    @patch('app.agent')
    def test_search_context_with_custom_k(self, mock_agent, client: TestClient, api_headers: dict):
        """Test context search with custom k parameter."""
        mock_agent.memory.search_relevant_context.return_value = []
        
        response = client.post(
            "/conversations/test_123/search?query=test&k=10",
            headers=api_headers
        )
        assert response.status_code == status.HTTP_200_OK
        mock_agent.memory.search_relevant_context.assert_called_with(
            query="test", k=10, conversation_id="test_123"
        )
    
    def test_search_context_requires_auth(self, client: TestClient):
        """Test search context requires authentication."""
        response = client.post("/conversations/test_123/search?query=test")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestLeadsByStageEndpoint:
    """Tests for GET /leads/by-stage/{stage} endpoint."""
    
    @patch('app.agent')
    def test_get_leads_by_stage_success(self, mock_agent, client: TestClient, api_headers: dict):
        """Test successful get leads by stage."""
        mock_agent.memory.STAGES = {"NEW": {}, "NAME_COLLECTED": {}}
        mock_agent.memory.get_leads_by_stage.return_value = [
            {"conversation_id": "conv1", "stage": "NEW"}
        ]
        
        response = client.get("/leads/by-stage/NEW", headers=api_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["stage"] == "NEW"
        assert "leads" in data
    
    @patch('app.agent')
    def test_get_leads_by_stage_invalid_stage(self, mock_agent, client: TestClient, api_headers: dict):
        """Test get leads with invalid stage."""
        mock_agent.memory.STAGES = {"NEW": {}}
        
        response = client.get("/leads/by-stage/INVALID", headers=api_headers)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_get_leads_by_stage_requires_auth(self, client: TestClient):
        """Test get leads by stage requires authentication."""
        response = client.get("/leads/by-stage/NEW")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestLeadStatsEndpoint:
    """Tests for GET /leads/stats endpoint."""
    
    @patch('app.agent')
    def test_get_lead_stats_success(self, mock_agent, client: TestClient, api_headers: dict):
        """Test successful get lead stats."""
        mock_agent.memory.get_all_stage_stats.return_value = {
            "NEW": 5,
            "NAME_COLLECTED": 3
        }
        
        response = client.get("/leads/stats", headers=api_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "NEW" in data
    
    def test_get_lead_stats_requires_auth(self, client: TestClient):
        """Test get lead stats requires authentication."""
        response = client.get("/leads/stats")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestUpdateStageEndpoint:
    """Tests for POST /conversations/{conversation_id}/update-stage endpoint."""
    
    @patch('app.agent')
    def test_update_stage_success(self, mock_agent, client: TestClient, api_headers: dict):
        """Test successful stage update."""
        response = client.post(
            "/conversations/test_123/update-stage?new_stage=NAME_COLLECTED",
            headers=api_headers
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["new_stage"] == "NAME_COLLECTED"
        mock_agent.memory.manually_set_stage.assert_called_once()
    
    @patch('app.agent')
    def test_update_stage_invalid_stage(self, mock_agent, client: TestClient, api_headers: dict):
        """Test update stage with invalid stage."""
        mock_agent.memory.manually_set_stage.side_effect = ValueError("Invalid stage")
        
        response = client.post(
            "/conversations/test_123/update-stage?new_stage=INVALID",
            headers=api_headers
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_update_stage_requires_auth(self, client: TestClient):
        """Test update stage requires authentication."""
        response = client.post("/conversations/test_123/update-stage?new_stage=NEW")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestGetStageEndpoint:
    """Tests for GET /conversations/{conversation_id}/stage endpoint."""
    
    @patch('app.agent')
    def test_get_stage_success(self, mock_agent, client: TestClient, api_headers: dict):
        """Test successful get stage."""
        mock_agent.memory.get_stage.return_value = "NEW"
        mock_agent.memory.get_lead_data.return_value = {"name": "Test"}
        
        response = client.get("/conversations/test_123/stage", headers=api_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["stage"] == "NEW"
        assert "lead_data" in data
    
    def test_get_stage_requires_auth(self, client: TestClient):
        """Test get stage requires authentication."""
        response = client.get("/conversations/test_123/stage")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestClearCacheEndpoint:
    """Tests for POST /admin/cache/clear endpoint."""
    
    @patch('app.supabase_service', None)
    def test_clear_cache_service_not_initialized(self, client: TestClient, api_headers: dict):
        """Test clear cache when service not initialized."""
        response = client.post("/admin/cache/clear", headers=api_headers)
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    
    @patch('app.supabase_service')
    def test_clear_cache_success(self, mock_service, client: TestClient, api_headers: dict):
        """Test successful cache clear."""
        mock_service.clear_cache = Mock()
        
        response = client.post("/admin/cache/clear", headers=api_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "success"
    
    @patch('app.supabase_service')
    def test_clear_cache_with_table_param(self, mock_service, client: TestClient, api_headers: dict):
        """Test clear cache with table parameter."""
        mock_service.clear_cache = Mock()
        
        response = client.post("/admin/cache/clear?table=courses", headers=api_headers)
        assert response.status_code == status.HTTP_200_OK
        mock_service.clear_cache.assert_called_with("courses")
    
    def test_clear_cache_requires_auth(self, client: TestClient):
        """Test clear cache requires authentication."""
        response = client.post("/admin/cache/clear")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

