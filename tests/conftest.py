"""Shared pytest fixtures for all tests."""
import os
import pytest
import tempfile
import shutil
from unittest.mock import Mock, MagicMock, patch
from typing import Generator

# Set test environment variables before any imports
os.environ["OPENAI_API_KEY"] = "test-openai-key"
os.environ["API_KEY"] = "test-api-key"
os.environ["SUPABASE_URL"] = "https://test.supabase.co"
os.environ["SUPABASE_KEY"] = "test-supabase-key"
os.environ["MODEL_NAME"] = "gpt-4.1-mini"
os.environ["TEMPERATURE"] = "0.7"
os.environ["MEMORY_DB_PATH"] = tempfile.mkdtemp(prefix="test_memory_")
os.environ["ENVIRONMENT"] = "test"

from core.agent import IntelligentChatAgent
from core.supabase_service import SupabaseService
from core.memory import LongTermMemory


@pytest.fixture
def temp_memory_db() -> Generator[str, None, None]:
    """Create a temporary directory for memory database."""
    temp_dir = tempfile.mkdtemp(prefix="test_memory_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def mock_supabase_service() -> Mock:
    """Create a mock Supabase service."""
    mock_service = Mock(spec=SupabaseService)
    
    # Mock common methods
    mock_service.get_course_links.return_value = {
        "demo_link": "https://example.com/demo",
        "pdf_link": "https://example.com/pdf",
        "course_link": "https://example.com/course"
    }
    
    mock_service.get_course_details.return_value = {
        "course_name": "Certified Tax Advisor (CTA)",
        "course_fee": "40000",
        "course_duration": "6 months",
        "professor_name": "Test Professor"
    }
    
    mock_service.get_faqs.return_value = [
        {"question": "What is the fee?", "answer": "Rs. 40,000"}
    ]
    
    mock_service.get_professor_info.return_value = {
        "name": "Test Professor",
        "qualifications": "CA, ACCA"
    }
    
    mock_service.get_company_info.return_value = {
        "company_name": "ICT",
        "phone_number": "+923001234567"
    }
    
    mock_service.search_courses.return_value = [
        {"course_name": "CTA", "description": "Tax course"}
    ]
    
    mock_service.append_lead_data.return_value = {
        "status": "success",
        "message": "Lead created",
        "lead_id": "test-lead-id"
    }
    
    return mock_service


@pytest.fixture
def mock_agent(mock_supabase_service: Mock, temp_memory_db: str) -> IntelligentChatAgent:
    """Create a test agent instance with mocked dependencies."""
    with patch('core.agent.ChatOpenAI') as mock_llm:
        mock_llm_instance = Mock()
        mock_llm.return_value = mock_llm_instance
        
        agent = IntelligentChatAgent(
            model_name="gpt-4.1-mini",
            temperature=0.7,
            memory_db_path=temp_memory_db,
            supabase_service=mock_supabase_service
        )
        
        # Mock the LLM invoke method
        agent.llm = mock_llm_instance
        
        return agent


@pytest.fixture
def test_conversation_id() -> str:
    """Return a test conversation ID."""
    return "test_conv_12345"


@pytest.fixture
def sample_chat_request() -> dict:
    """Sample chat request payload."""
    return {
        "message": "Hello, I want to know about CTA course",
        "conversation_id": "test_conv_12345"
    }


@pytest.fixture
def sample_lead_data() -> dict:
    """Sample lead data."""
    return {
        "name": "Test User",
        "phone": "03001234567",
        "selected_course": "Certified Tax Advisor (CTA)",
        "education_level": "Bachelors",
        "goal": "Career growth"
    }


@pytest.fixture
def api_headers() -> dict:
    """API headers with authentication."""
    return {
        "X-API-Key": "test-api-key",
        "Content-Type": "application/json"
    }

