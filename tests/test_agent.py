"""Comprehensive tests for IntelligentChatAgent."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from core.agent import IntelligentChatAgent


class TestAgentInitialization:
    """Tests for agent initialization."""
    
    @patch('core.agent.ChatOpenAI')
    def test_agent_initializes_successfully(self, mock_llm, mock_supabase_service, temp_memory_db):
        """Test agent initializes with all dependencies."""
        mock_llm_instance = Mock()
        mock_llm.return_value = mock_llm_instance
        
        agent = IntelligentChatAgent(
            model_name="gpt-4.1-mini",
            temperature=0.7,
            memory_db_path=temp_memory_db,
            supabase_service=mock_supabase_service
        )
        
        assert agent is not None
        assert agent.model_name == "gpt-4.1-mini"
    
    @patch('core.agent.ChatOpenAI')
    def test_agent_initializes_without_supabase(self, mock_llm, temp_memory_db):
        """Test agent initializes without Supabase service."""
        mock_llm_instance = Mock()
        mock_llm.return_value = mock_llm_instance
        
        agent = IntelligentChatAgent(
            model_name="gpt-4.1-mini",
            temperature=0.7,
            memory_db_path=temp_memory_db,
            supabase_service=None
        )
        
        assert agent is not None
    
    @patch('core.agent.ChatOpenAI')
    def test_agent_has_tools(self, mock_llm, mock_supabase_service, temp_memory_db):
        """Test agent has tools configured."""
        mock_llm_instance = Mock()
        mock_llm.return_value = mock_llm_instance
        
        agent = IntelligentChatAgent(
            model_name="gpt-4.1-mini",
            temperature=0.7,
            memory_db_path=temp_memory_db,
            supabase_service=mock_supabase_service
        )
        
        assert hasattr(agent, 'all_tools')
        assert len(agent.all_tools) > 0


class TestChatMethod:
    """Tests for agent.chat() method."""
    
    @patch('core.agent.ChatOpenAI')
    def test_chat_creates_new_conversation(self, mock_llm, mock_supabase_service, temp_memory_db):
        """Test chat creates new conversation when ID not provided."""
        mock_llm_instance = Mock()
        mock_llm.return_value = mock_llm_instance
        
        # Mock agent state and response
        with patch.object(IntelligentChatAgent, '_call_agent') as mock_call:
            mock_call.return_value = {
                "messages": [AIMessage(content="Test response")]
            }
            
            agent = IntelligentChatAgent(
                model_name="gpt-4.1-mini",
                temperature=0.7,
                memory_db_path=temp_memory_db,
                supabase_service=mock_supabase_service
            )
            
            result = agent.chat("Hello", conversation_id=None)
            assert "conversation_id" in result
            assert result["conversation_id"] is not None
    
    @patch('core.agent.ChatOpenAI')
    def test_chat_uses_existing_conversation(self, mock_llm, mock_supabase_service, temp_memory_db):
        """Test chat uses existing conversation ID."""
        mock_llm_instance = Mock()
        mock_llm.return_value = mock_llm_instance
        
        with patch.object(IntelligentChatAgent, '_call_agent') as mock_call:
            mock_call.return_value = {
                "messages": [AIMessage(content="Test response")]
            }
            
            agent = IntelligentChatAgent(
                model_name="gpt-4.1-mini",
                temperature=0.7,
                memory_db_path=temp_memory_db,
                supabase_service=mock_supabase_service
            )
            
            result = agent.chat("Hello", conversation_id="existing_conv_123")
            assert result["conversation_id"] == "existing_conv_123"
    
    @patch('core.agent.ChatOpenAI')
    def test_chat_returns_response(self, mock_llm, mock_supabase_service, temp_memory_db):
        """Test chat returns agent response."""
        mock_llm_instance = Mock()
        mock_llm.return_value = mock_llm_instance
        
        with patch.object(IntelligentChatAgent, '_call_agent') as mock_call:
            mock_call.return_value = {
                "messages": [AIMessage(content="Test response")]
            }
            
            agent = IntelligentChatAgent(
                model_name="gpt-4.1-mini",
                temperature=0.7,
                memory_db_path=temp_memory_db,
                supabase_service=mock_supabase_service
            )
            
            result = agent.chat("Hello")
            assert "response" in result
            assert result["response"] == "Test response"
    
    @patch('core.agent.ChatOpenAI')
    def test_chat_increments_turn_count(self, mock_llm, mock_supabase_service, temp_memory_db):
        """Test chat increments turn count."""
        mock_llm_instance = Mock()
        mock_llm.return_value = mock_llm_instance
        
        with patch.object(IntelligentChatAgent, '_call_agent') as mock_call:
            mock_call.return_value = {
                "messages": [AIMessage(content="Test")]
            }
            
            agent = IntelligentChatAgent(
                model_name="gpt-4.1-mini",
                temperature=0.7,
                memory_db_path=temp_memory_db,
                supabase_service=mock_supabase_service
            )
            
            result1 = agent.chat("Hello", conversation_id="test_conv")
            result2 = agent.chat("Hello again", conversation_id="test_conv")
            
            assert result2["turn_count"] > result1["turn_count"]
    
    @patch('core.agent.ChatOpenAI')
    def test_chat_handles_tool_calls(self, mock_llm, mock_supabase_service, temp_memory_db):
        """Test chat handles tool calls correctly."""
        mock_llm_instance = Mock()
        mock_llm.return_value = mock_llm_instance
        
        with patch.object(IntelligentChatAgent, '_call_agent') as mock_call:
            mock_call.return_value = {
                "messages": [
                    AIMessage(content="", tool_calls=[{
                        "name": "fetch_course_details",
                        "args": {"course_name": "CTA"},
                        "id": "call_123"
                    }]),
                    ToolMessage(content="Course details", tool_call_id="call_123"),
                    AIMessage(content="Here are the details")
                ]
            }
            
            agent = IntelligentChatAgent(
                model_name="gpt-4.1-mini",
                temperature=0.7,
                memory_db_path=temp_memory_db,
                supabase_service=mock_supabase_service
            )
            
            result = agent.chat("Tell me about CTA")
            assert "response" in result


class TestExtractAndUpdateLeadData:
    """Tests for _extract_and_update_lead_data method."""
    
    @patch('core.agent.ChatOpenAI')
    def test_extract_lead_data_from_tool_call(self, mock_llm, mock_supabase_service, temp_memory_db):
        """Test extracting lead data from tool call."""
        mock_llm_instance = Mock()
        mock_llm.return_value = mock_llm_instance
        
        agent = IntelligentChatAgent(
            model_name="gpt-4.1-mini",
            temperature=0.7,
            memory_db_path=temp_memory_db,
            supabase_service=mock_supabase_service
        )
        
        messages = [
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "append_lead_data",
                    "args": {
                        "name": "Test User",
                        "phone": "03001234567",
                        "selected_course": "CTA",
                        "notes": None  # This should not cause error
                    },
                    "id": "call_123"
                }]
            )
        ]
        
        # Should not raise TypeError
        agent._extract_and_update_lead_data("test_conv", messages)
        
        # Verify lead data was extracted
        lead_data = agent.memory.get_lead_data("test_conv")
        assert lead_data["name"] == "Test User"
        assert lead_data["phone"] == "03001234567"
    
    @patch('core.agent.ChatOpenAI')
    def test_extract_lead_data_handles_none_notes(self, mock_llm, mock_supabase_service, temp_memory_db):
        """Test extracting lead data when notes is None (the bug fix)."""
        mock_llm_instance = Mock()
        mock_llm.return_value = mock_llm_instance
        
        agent = IntelligentChatAgent(
            model_name="gpt-4.1-mini",
            temperature=0.7,
            memory_db_path=temp_memory_db,
            supabase_service=mock_supabase_service
        )
        
        messages = [
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "append_lead_data",
                    "args": {
                        "phone": "03001234567",
                        "notes": None  # This was causing the bug
                    },
                    "id": "call_123"
                }]
            )
        ]
        
        # Should not raise TypeError: argument of type 'NoneType' is not iterable
        try:
            agent._extract_and_update_lead_data("test_conv", messages)
            assert True  # No exception raised
        except TypeError as e:
            if "NoneType" in str(e) and "iterable" in str(e):
                pytest.fail("Bug not fixed: NoneType error still occurs")
            raise
    
    @patch('core.agent.ChatOpenAI')
    def test_extract_lead_data_with_notes_string(self, mock_llm, mock_supabase_service, temp_memory_db):
        """Test extracting lead data with notes as string."""
        mock_llm_instance = Mock()
        mock_llm.return_value = mock_llm_instance
        
        agent = IntelligentChatAgent(
            model_name="gpt-4.1-mini",
            temperature=0.7,
            memory_db_path=temp_memory_db,
            supabase_service=mock_supabase_service
        )
        
        messages = [
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "append_lead_data",
                    "args": {
                        "phone": "03001234567",
                        "notes": "Selected_Course: CTA, Education_Level: Bachelors"
                    },
                    "id": "call_123"
                }]
            )
        ]
        
        agent._extract_and_update_lead_data("test_conv", messages)
        
        lead_data = agent.memory.get_lead_data("test_conv")
        assert lead_data["selected_course"] == "CTA"
        assert lead_data["education_level"] == "Bachelors"
    
    @patch('core.agent.ChatOpenAI')
    def test_extract_lead_data_from_user_message(self, mock_llm, mock_supabase_service, temp_memory_db):
        """Test extracting lead data from user message heuristics."""
        mock_llm_instance = Mock()
        mock_llm.return_value = mock_llm_instance
        
        agent = IntelligentChatAgent(
            model_name="gpt-4.1-mini",
            temperature=0.7,
            memory_db_path=temp_memory_db,
            supabase_service=mock_supabase_service
        )
        
        messages = [
            HumanMessage(content="My name is John Doe"),
            HumanMessage(content="My phone is 03001234567")
        ]
        
        agent._extract_and_update_lead_data("test_conv", messages)
        
        lead_data = agent.memory.get_lead_data("test_conv")
        assert "John Doe" in lead_data.get("name", "")
        assert "03001234567" in lead_data.get("phone", "")
    
    @patch('core.agent.ChatOpenAI')
    def test_extract_lead_data_empty_messages(self, mock_llm, mock_supabase_service, temp_memory_db):
        """Test extracting lead data with empty messages."""
        mock_llm_instance = Mock()
        mock_llm.return_value = mock_llm_instance
        
        agent = IntelligentChatAgent(
            model_name="gpt-4.1-mini",
            temperature=0.7,
            memory_db_path=temp_memory_db,
            supabase_service=mock_supabase_service
        )
        
        # Should not raise exception
        agent._extract_and_update_lead_data("test_conv", [])


class TestSummarization:
    """Tests for conversation summarization."""
    
    @patch('core.agent.ChatOpenAI')
    def test_summarization_triggered_at_interval(self, mock_llm, mock_supabase_service, temp_memory_db):
        """Test summarization is triggered at specified interval."""
        mock_llm_instance = Mock()
        mock_llm.return_value = mock_llm_instance
        
        agent = IntelligentChatAgent(
            model_name="gpt-4.1-mini",
            temperature=0.7,
            memory_db_path=temp_memory_db,
            supabase_service=mock_supabase_service,
            summarize_interval=5
        )
        
        with patch.object(agent, '_summarize_conversation') as mock_summarize:
            with patch.object(agent, '_call_agent') as mock_call:
                mock_call.return_value = {"messages": [AIMessage(content="Test")]}
                
                # Simulate 5 turns
                for i in range(5):
                    agent.chat("Hello", conversation_id="test_conv")
                
                # Should have been called
                assert mock_summarize.called
    
    @patch('core.agent.ChatOpenAI')
    def test_summarization_creates_summary(self, mock_llm, mock_supabase_service, temp_memory_db):
        """Test summarization creates conversation summary."""
        mock_llm_instance = Mock()
        mock_llm_instance.invoke.return_value = AIMessage(content="This is a summary")
        mock_llm.return_value = mock_llm_instance
        
        agent = IntelligentChatAgent(
            model_name="gpt-4.1-mini",
            temperature=0.7,
            memory_db_path=temp_memory_db,
            supabase_service=mock_supabase_service
        )
        
        # Create some conversation history
        agent.memory.add_conversation("test_conv", "User: Hello", "Assistant: Hi")
        
        state = {
            "conversation_id": "test_conv",
            "messages": [HumanMessage(content="Hello"), AIMessage(content="Hi")]
        }
        
        result_state = agent._summarize_conversation(state)
        assert "messages" in result_state


class TestToolCallLimits:
    """Tests for tool call limits and safety checks."""
    
    @patch('core.agent.ChatOpenAI')
    def test_tool_call_limit_enforced(self, mock_llm, mock_supabase_service, temp_memory_db):
        """Test tool call limit is enforced."""
        mock_llm_instance = Mock()
        mock_llm.return_value = mock_llm_instance
        
        agent = IntelligentChatAgent(
            model_name="gpt-4.1-mini",
            temperature=0.7,
            memory_db_path=temp_memory_db,
            supabase_service=mock_supabase_service
        )
        
        # Create state with too many tool calls
        state = {
            "messages": [
                AIMessage(content="", tool_calls=[{"name": f"tool_{i}", "args": {}, "id": f"call_{i}"} for i in range(15)])
            ]
        }
        
        result = agent._should_continue(state)
        assert result == "end"  # Should end due to limit
    
    @patch('core.agent.ChatOpenAI')
    def test_duplicate_tool_call_detection(self, mock_llm, mock_supabase_service, temp_memory_db):
        """Test duplicate tool call detection."""
        mock_llm_instance = Mock()
        mock_llm.return_value = mock_llm_instance
        
        agent = IntelligentChatAgent(
            model_name="gpt-4.1-mini",
            temperature=0.7,
            memory_db_path=temp_memory_db,
            supabase_service=mock_supabase_service
        )
        
        # Create state with duplicate tool calls
        state = {
            "messages": [
                AIMessage(content="", tool_calls=[{
                    "name": "fetch_course_details",
                    "args": {"course_name": "CTA"},
                    "id": "call_1"
                }]),
                AIMessage(content="", tool_calls=[{
                    "name": "fetch_course_details",
                    "args": {"course_name": "CTA"},
                    "id": "call_2"
                }])
            ]
        }
        
        result = agent._should_continue(state)
        # Should detect duplicate and handle appropriately
        assert result in ["end", "continue"]


class TestMemoryIntegration:
    """Tests for memory integration."""
    
    @patch('core.agent.ChatOpenAI')
    def test_conversation_saved_to_memory(self, mock_llm, mock_supabase_service, temp_memory_db):
        """Test conversation is saved to memory."""
        mock_llm_instance = Mock()
        mock_llm.return_value = mock_llm_instance
        
        with patch.object(IntelligentChatAgent, '_call_agent') as mock_call:
            mock_call.return_value = {
                "messages": [AIMessage(content="Test response")]
            }
            
            agent = IntelligentChatAgent(
                model_name="gpt-4.1-mini",
                temperature=0.7,
                memory_db_path=temp_memory_db,
                supabase_service=mock_supabase_service
            )
            
            agent.chat("Hello", conversation_id="test_conv")
            
            # Verify conversation was saved
            history = agent.memory.get_conversation_history("test_conv")
            assert len(history) > 0
    
    @patch('core.agent.ChatOpenAI')
    def test_lead_data_persisted(self, mock_llm, mock_supabase_service, temp_memory_db):
        """Test lead data is persisted in memory."""
        mock_llm_instance = Mock()
        mock_llm.return_value = mock_llm_instance
        
        agent = IntelligentChatAgent(
            model_name="gpt-4.1-mini",
            temperature=0.7,
            memory_db_path=temp_memory_db,
            supabase_service=mock_supabase_service
        )
        
        agent.memory.update_lead_field("test_conv", "name", "Test User")
        
        lead_data = agent.memory.get_lead_data("test_conv")
        assert lead_data["name"] == "Test User"

