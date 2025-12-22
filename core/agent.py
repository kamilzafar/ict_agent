"""LangGraph agent with long-term memory and summarization."""
import os
import re
import uuid
import logging
from typing import Annotated, TypedDict, List, Dict, Any, Optional, TYPE_CHECKING
from datetime import datetime

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.sheets_cache import GoogleSheetsCacheService

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, trim_messages
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

from core.memory import LongTermMemory
from tools.mcp_rag_tools import get_mcp_rag_tools
from tools.sheets_tools import create_google_sheets_tools
from tools.template_tools import template_tools
from core.context_injector import ContextInjector


class AgentState(TypedDict):
    """State for the LangGraph agent."""
    messages: Annotated[List[BaseMessage], add_messages]
    conversation_id: str
    turn_count: int
    context: List[Dict[str, Any]]


class IntelligentChatAgent:
    """Intelligent chat agent with long-term memory and summarization."""
    
    def __init__(
        self,
        model_name: str = "gpt-4.1-mini",  # Changed to gpt-4.1-mini for 128k context window
        temperature: float = 0.7,
        memory_db_path: str = "/app/memory_db",
        summarize_interval: int = 10,
        sheets_cache_service: Optional[Any] = None
    ):
        """Initialize the agent.
        
        Args:
            model_name: Name of the LLM model to use
            temperature: Temperature for the LLM
            memory_db_path: Path to the memory database
            summarize_interval: Number of turns before summarizing
            sheets_cache_service: Optional Google Sheets cache service instance
        """
        self.memory = LongTermMemory(persist_directory=memory_db_path)
        self.summarize_interval = summarize_interval
        
        # Initialize context injector if cache service is provided
        self.context_injector = None
        if sheets_cache_service:
            self.context_injector = ContextInjector(sheets_cache_service)
        
        # Load system prompt once at initialization (CACHING OPTIMIZATION)
        # This avoids reading from disk on every API call
        self.base_system_prompt = self._load_system_prompt()
        
        # Initialize LLM using OpenAI (required)
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable is required. "
                "Please set it in your .env file or environment variables."
            )
        
        try:
            self.llm = ChatOpenAI(
                model=model_name,
                temperature=temperature,
                openai_api_key=api_key
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to initialize OpenAI LLM: {str(e)}. "
                "Please check your OPENAI_API_KEY is valid and the model name is correct."
            ) from e
        
        # Get available tools (MCP RAG tools + Google Sheets tools + Template tools)
        self.mcp_rag_tools = get_mcp_rag_tools(sheets_cache_service)
        self.sheets_tools = create_google_sheets_tools(sheets_cache_service) if sheets_cache_service else []
        self.template_tools = template_tools  # Always available

        # Combine all tools
        all_tools = self.mcp_rag_tools + self.sheets_tools + self.template_tools
        
        # Bind tools to LLM if available
        if all_tools:
            self.llm_with_tools = self.llm.bind_tools(all_tools)
        else:
            self.llm_with_tools = self.llm
        
        # Store tools for graph creation
        self.all_tools = all_tools
        
        # Create the graph
        self.graph = self._create_graph()
        
        # Compile the graph with memory
        self.checkpointer = MemorySaver()
        self.app = self.graph.compile(checkpointer=self.checkpointer)
    
    def _load_system_prompt(self) -> str:
        """Load system prompt once at startup and cache it.
        
        This method is called once during initialization to load the prompt
        from disk and store it in memory. This avoids file I/O on every
        API request, improving performance significantly.
        
        Returns:
            Base system prompt content from prompt.txt file
        """
        prompt_file = os.path.join(os.path.dirname(__file__), "..", "config", "prompt.txt")
        prompt_file = os.path.normpath(prompt_file)  # Normalize path for cross-platform compatibility
        try:
            with open(prompt_file, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            # Fallback if prompt.txt doesn't exist
            return """You are Tanveer Awan, an Enrollment Advisor at Institute of Corporate & Taxation (ICT).
You are a real human - not an AI. Never break character.
You help leads with course enrollment through WhatsApp conversations."""
    
    def _create_graph(self) -> StateGraph:
        """Create the LangGraph state graph."""
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("retrieve_context", self._retrieve_context)
        workflow.add_node("agent", self._call_agent)
        
        # Add tools node if tools are available
        if self.all_tools:
            workflow.add_node("tools", ToolNode(self.all_tools))
        
        workflow.add_node("summarize", self._summarize_conversation)
        
        # Set entry point
        workflow.set_entry_point("retrieve_context")
        
        # Add edges
        workflow.add_edge("retrieve_context", "agent")
        
        # Conditional edge from agent: check if tool calls are needed, summarize, or end
        workflow.add_conditional_edges(
            "agent",
            self._should_continue,
            {
                "continue": "tools" if self.all_tools else "end",
                "end": END,
                "summarize": "summarize"
            }
        )
        
        # After tools, go back to agent
        if self.all_tools:
            workflow.add_edge("tools", "agent")
        
        # After summarize, end
        workflow.add_edge("summarize", END)
        
        return workflow
    
    def _retrieve_context(self, state: AgentState) -> AgentState:
        """Retrieve relevant context from long-term memory.
        
        Follows LangChain best practices:
        - Stores summary in state for injection as context memory (not system prompt)
        - Retrieves recent unsummarized conversation history
        - Prepares context for efficient message injection
        """
        conversation_id = state.get("conversation_id")
        
        if not conversation_id:
            return state
        
        # Get conversation summary (all summarized turns - cumulative)
        # This will be injected as context memory, not in system prompt
        current_summary = self.memory.get_conversation_summary(conversation_id)
        
        # Get recent conversation history (unsummarized turns) from memory
        all_history = self.memory.get_conversation_history(conversation_id)
        turn_count = len(all_history)
        
        # Calculate which turns are unsummarized
        recent_history = []
        if turn_count > 0:
            num_complete_cycles = turn_count // self.summarize_interval
            if num_complete_cycles > 0:
                turns_since_last_summary = turn_count % self.summarize_interval
                if turns_since_last_summary == 0:
                    # At a summarization point, include these turns
                    recent_history = all_history[-self.summarize_interval:]
                else:
                    # Only unsummarized turns remain
                    recent_history = all_history[-turns_since_last_summary:]
            else:
                # No summarization yet, all turns are recent
                recent_history = all_history
        
        # Store summary and recent history in state for efficient access
        # Summary will be injected as context memory message
        state["conversation_summary"] = current_summary
        state["recent_history"] = recent_history
        
        # Store context documents for response tracking
        # This ensures context is always available in the response
        from langchain_core.documents import Document
        context_docs = []
        if current_summary:
            context_docs.append({
                "content": current_summary,
                "metadata": {
                    "conversation_id": conversation_id,
                    "type": "summary",
                    "covers_all_summarized_turns": True
                }
            })
        if recent_history:
            for turn in recent_history:
                context_docs.append({
                    "content": f"User: {turn.get('user_message', '')}\nAssistant: {turn.get('assistant_message', '')}",
                    "metadata": {
                        "conversation_id": conversation_id,
                        "type": "recent_unsummarized_turn",
                        "timestamp": turn.get("timestamp", "")
                    }
                })
        
        # Always set context (even if empty) to ensure it's available in response
        state["context"] = context_docs
        
        # Log context retrieval for debugging
        logger.debug(f"Retrieved context for {conversation_id}: summary={current_summary is not None}, recent_turns={len(recent_history)}, context_docs={len(context_docs)}")
        
        return state
    
    def _call_agent(self, state: AgentState) -> AgentState:
        """Call the agent LLM with full context using LangChain best practices.
        
        Efficiently provides:
        - Summary as context memory (injected as message, not system prompt)
        - ALL unsummarized messages sent to LLM
        - Uses trim_messages for efficient message handling
        """
        messages = state["messages"]
        conversation_id = state.get("conversation_id")
        
        # Get base system prompt (without summary/context - that goes as memory)
        system_prompt = self._get_system_prompt(state)
        system_message = SystemMessage(content=system_prompt)
        
        # Filter out system messages (they're already in the system prompt)
        conversation_messages = [
            msg for msg in messages 
            if not isinstance(msg, SystemMessage)
        ]
        
        # Get summary from state (retrieved by _retrieve_context)
        # Inject summary as context memory (not in system prompt)
        summary = state.get("conversation_summary")
        context_messages = []
        
        if summary:
            # Inject summary as a context message for the LLM
            # This follows LangChain best practices: context as memory, not system prompt
            summary_context = SystemMessage(
                content=f"[Conversation Summary - Context Memory]\n\nThis is a summary of all previous conversation turns that have been summarized:\n\n{summary}\n\nUse this summary to understand the full conversation history. The messages below are recent unsummarized turns."
            )
            context_messages.append(summary_context)
        
        # Calculate which messages are unsummarized
        # We want to send ALL unsummarized messages to the LLM
        all_history = self.memory.get_conversation_history(conversation_id)
        turn_count = len(all_history)
        
        # Determine unsummarized messages
        if turn_count > 0:
            num_complete_cycles = turn_count // self.summarize_interval
            if num_complete_cycles > 0:
                turns_since_last_summary = turn_count % self.summarize_interval
                if turns_since_last_summary == 0:
                    # At summarization point, keep last summarize_interval turns
                    unsummarized_turns = self.summarize_interval
                else:
                    # Keep only unsummarized turns
                    unsummarized_turns = turns_since_last_summary
            else:
                # No summarization yet, all turns are unsummarized
                unsummarized_turns = turn_count
        else:
            unsummarized_turns = 0
        
        # Calculate messages to keep: ALL unsummarized messages
        # Each turn = 2 messages (user + assistant)
        unsummarized_message_count = unsummarized_turns * 2
        
        # Use LangChain's trim_messages for efficient trimming
        # Keep all unsummarized messages, plus a safety buffer
        if len(conversation_messages) > unsummarized_message_count:
            # Use trim_messages to efficiently keep only unsummarized messages
            # This follows LangChain best practices for message trimming
            trimmed = trim_messages(
                conversation_messages,
                max_tokens=unsummarized_message_count + (self.summarize_interval * 2),  # Safety buffer
                strategy="last",  # Keep last N messages
                token_counter=len,  # Count by message count
                start_on="human",  # Ensure valid conversation structure
                include_system=False,  # System message is separate
                allow_partial=False  # Don't break message pairs
            )
            conversation_messages = trimmed if trimmed else conversation_messages[-unsummarized_message_count:]
            logger.debug(f"Trimmed to {len(conversation_messages)} unsummarized messages (covering {unsummarized_turns} turns)")
        else:
            # All messages are unsummarized, keep them all
            logger.debug(f"Keeping all {len(conversation_messages)} messages (all unsummarized)")
        
        # Prepare final messages following LangChain best practices:
        # 1. System prompt (base instructions, tools, metadata - NO summary)
        # 2. Summary as context memory (injected as message)
        # 3. All unsummarized messages (actual conversation)
        agent_messages = [system_message] + context_messages + conversation_messages
        
        # Call LLM with full context
        response = self.llm_with_tools.invoke(agent_messages)
        
        # Add response to messages
        state["messages"].append(response)
        
        return state
    
    def _get_system_prompt(self, state: AgentState) -> str:
        """Get the system prompt for the agent.
        
        NOTE: Summary is NOT included here - it's injected as context memory in _call_agent
        This keeps the system prompt focused on instructions, tools, and metadata.
        """
        conversation_id = state.get("conversation_id", "unknown")
        turn_count = state.get("turn_count", 0)
        
        # Use cached system prompt (loaded once at initialization)
        # This avoids file I/O on every request, improving performance
        base_prompt = self.base_system_prompt
        
        # Add tool information
        tool_info = ""
        if self.all_tools:
            tool_descriptions = []
            
            # MCP RAG tool (for saving data)
            if self.mcp_rag_tools:
                tool_descriptions.append("append_lead_to_rag_sheets - Save lead data to Leads sheet. Do NOT use to fetch links or course data.")
            
            # Sheet tools (for fetching data)
            if self.sheets_tools:
                tool_descriptions.append("fetch_course_links - Get demo links, PDF links, or course page links from Course_Links sheet")
                tool_descriptions.append("fetch_course_details - Get course information (fees, duration, dates, professor, locations) from Course_Details sheet")
                tool_descriptions.append("fetch_faqs - Get FAQs from FAQs sheet")
                tool_descriptions.append("fetch_professor_info - Get professor/trainer information from About_Profr sheet")
                tool_descriptions.append("fetch_company_info - Get company information (contact, social media, locations) from Company_Info sheet")
            
            if tool_descriptions:
                tool_info = f"\n\n## AVAILABLE TOOLS:\n\nYou have access to the following tools:\n"
                for desc in tool_descriptions:
                    tool_info += f"- {desc}\n"
                tool_info += "\nIMPORTANT TOOL USAGE RULES:\n"
                tool_info += "- To GET links (demo, PDF, course page) → Use fetch_course_links\n"
                tool_info += "- To GET course information → Use fetch_course_details\n"
                tool_info += "- To GET FAQs → Use fetch_faqs\n"
                tool_info += "- To GET professor info → Use fetch_professor_info\n"
                tool_info += "- To GET company info → Use fetch_company_info\n"
                tool_info += "- To SAVE lead data → Use append_lead_to_rag_sheets (only before sharing demo video link in Step 6)\n"
                tool_info += "\nNEVER use append_lead_to_rag_sheets to fetch links or course data - it only saves data.\n"
        
        # Add Google Sheets context injection (proactive - no tool calls needed)
        sheets_context = ""
        if self.context_injector:
            # Get current stage and selected course
            current_stage = self.memory.get_stage(conversation_id)
            lead_data = self.memory.get_lead_data(conversation_id)
            selected_course = lead_data.get("selected_course")
            
            # Inject stage-based context
            stage_context = self.context_injector.get_stage_context(
                current_stage,
                selected_course=selected_course
            )
            
            if stage_context:
                sheets_context = f"\n\n## RELEVANT GOOGLE SHEETS DATA (Pre-loaded for your reference):\n{stage_context}\n"
                sheets_context += "NOTE: This data is automatically loaded from Google Sheets cache. You can use this information directly without calling any tools.\n"
        
        # Add conversation metadata
        context_info = f"""
## CURRENT CONVERSATION METADATA:
- Conversation ID: {conversation_id}
- Turn Count: {turn_count}
- Note: Conversation summary is provided as context memory (not in this system prompt)
"""
        
        # Combine prompt (NO summary here - it's injected as context memory)
        full_prompt = base_prompt + tool_info + context_info + sheets_context
        
        return full_prompt
    
    def _should_continue(self, state: AgentState) -> str:
        """Determine if we should continue (call tools), summarize, or end."""
        messages = state["messages"]
        last_message = messages[-1]
        
        # If the last message has tool calls, continue to tools
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            return "continue"
        
        # Check if we should summarize (every N turns)
        # Summarize AFTER every N messages (e.g., after turn 10, 20, 30, etc.)
        turn_count = state.get("turn_count", 0)
        
        # Only summarize when we've completed a full interval (turn 10, 20, 30, etc.)
        # turn_count is 1-indexed (turn 1, 2, 3, ..., 10, 11, ...)
        # So we summarize after turn 10, 20, 30, etc.
        if turn_count >= self.summarize_interval and turn_count % self.summarize_interval == 0:
            logger.info(f"Triggering summarization: turn_count={turn_count}, interval={self.summarize_interval}")
            return "summarize"
        
        # Otherwise, end (response is complete)
        return "end"
    
    def _summarize_conversation(self, state: AgentState) -> AgentState:
        """Summarize the last N messages and remove them from state."""
        conversation_id = state.get("conversation_id")
        messages = state["messages"]
        
        if not conversation_id:
            return state
        
        # Filter out system messages and tool call messages
        conversation_messages = [
            msg for msg in messages 
            if not isinstance(msg, SystemMessage) 
            and not (hasattr(msg, 'tool_calls') and msg.tool_calls)
        ]
        
        # Only summarize the last N messages (where N = summarize_interval)
        # These are the messages that haven't been summarized yet
        if len(conversation_messages) < self.summarize_interval:
            # Not enough messages to summarize yet, skip
            return state
        
        messages_to_summarize = conversation_messages[-self.summarize_interval:]
        
        # Extract conversation text from messages to summarize
        conversation_text = self._extract_conversation_text(messages_to_summarize)
        
        # Get existing summary to create cumulative summary
        existing_summary = self.memory.get_conversation_summary(conversation_id)
        
        # Create summarization prompt
        if existing_summary:
            summary_prompt = f"""Previous conversation summary:
{existing_summary}

New conversation turns to add:
{conversation_text}

Please update the summary to include the new information. Keep it concise and focused on key topics, decisions, and important information.

Updated Summary:"""
        else:
            summary_prompt = f"""Please provide a concise summary of the following conversation. 
Focus on key topics, decisions, and important information that should be remembered for future interactions.

Conversation:
{conversation_text}

Summary:"""
        
        # Generate summary
        summary_messages = [
            SystemMessage(content="You are a helpful assistant that creates concise conversation summaries."),
            HumanMessage(content=summary_prompt)
        ]
        summary_response = self.llm.invoke(summary_messages)
        summary = summary_response.content
        
        # Save summary to memory (this updates/replaces the old one)
        self.memory.add_summary(conversation_id, summary)
        
        # IMPORTANT: Don't remove summarized messages from state
        # The unsummarized messages (since last summary) should remain in context
        # The summary is stored in memory and will be loaded in future turns via get_conversation_summary()
        # But the recent unsummarized messages stay in the conversation for immediate context
        
        # Log summarization for debugging
        turn_count = state.get("turn_count", 0)
        start_turn = turn_count - self.summarize_interval + 1
        end_turn = turn_count
        logger.info(f"✓ Summarized turns {start_turn}-{end_turn} for conversation {conversation_id}")
        logger.info(f"  Summary length: {len(summary)} characters")
        logger.info(f"  Unsummarized messages remain in context for next turns")
        
        # Don't modify messages - keep them in state for context
        # The summary will be loaded in future turns via get_conversation_summary()
        # The unsummarized messages (turns since last summary) will be loaded in chat() method
        return state

    def _extract_and_update_lead_data(self, conversation_id: str, messages: List[BaseMessage]):
        """Extract lead data from conversation and update stages.

        Args:
            conversation_id: Conversation ID
            messages: List of messages from the conversation
        """
        # Always work with the latest lead_data snapshot to avoid redundant writes
        lead_data_snapshot = self.memory.get_lead_data(conversation_id)

        # Check for tool calls (especially append_lead_to_rag_sheets)
        for message in messages:
            if hasattr(message, 'tool_calls') and message.tool_calls:
                for tool_call in message.tool_calls:
                    if tool_call.get('name') == 'append_lead_to_rag_sheets':
                        # Extract lead data from tool call arguments
                        args = tool_call.get('args', {})

                        if args.get('name'):
                            self.memory.update_lead_field(conversation_id, 'name', args['name'])

                        if args.get('phone'):
                            self.memory.update_lead_field(conversation_id, 'phone', args['phone'])

                        # Mark demo as shared when this tool is called
                        self.memory.update_lead_field(conversation_id, 'demo_shared', True)

                        # Extract other data from notes or metadata
                        notes = args.get('notes', '')
                        metadata = args.get('metadata', {})

                        # Try to extract course from notes or metadata
                        if 'Selected_Course:' in notes:
                            course = notes.split('Selected_Course:')[1].split(',')[0].strip()
                            self.memory.update_lead_field(conversation_id, 'selected_course', course)
                        elif metadata.get('course'):
                            self.memory.update_lead_field(conversation_id, 'selected_course', metadata['course'])

                        # Try to extract education level
                        if 'Education_Level:' in notes:
                            education = notes.split('Education_Level:')[1].split(',')[0].strip()
                            self.memory.update_lead_field(conversation_id, 'education_level', education)
                        elif metadata.get('education'):
                            self.memory.update_lead_field(conversation_id, 'education_level', metadata['education'])

                        # Try to extract goal
                        if 'Goal_Motivation:' in notes:
                            goal = notes.split('Goal_Motivation:')[1].split(',')[0].strip()
                            self.memory.update_lead_field(conversation_id, 'goal', goal)
                        elif metadata.get('goal'):
                            self.memory.update_lead_field(conversation_id, 'goal', metadata['goal'])

        # Work only with user-authored text for heuristics to avoid picking up assistant prompts
        # Get the MOST RECENT user message for better detection
        user_text = ""
        for msg in reversed(messages):  # Start from most recent
            if isinstance(msg, HumanMessage) and hasattr(msg, "content"):
                user_text = msg.content  # Use only the most recent message
                break
        
        # Also collect all user messages for comprehensive analysis
        all_user_text = ""
        for msg in messages:
            if isinstance(msg, HumanMessage) and hasattr(msg, "content"):
                all_user_text += msg.content + " "

        user_text_lower = user_text.lower()
        all_user_text_lower = all_user_text.lower()

        # Basic name extraction when tool data is not available
        # Check both recent message and all messages
        if not lead_data_snapshot.get("name"):
            # Try recent message first
            name_match = re.search(r"(?:my name is|i am|i'm|this is|mera naam|main)\s+([A-Za-z][A-Za-z\s]{1,40})", user_text, re.IGNORECASE)
            if not name_match:
                # Try all messages
                name_match = re.search(r"(?:my name is|i am|i'm|this is|mera naam|main)\s+([A-Za-z][A-Za-z\s]{1,40})", all_user_text, re.IGNORECASE)
            if name_match:
                candidate = name_match.group(1).strip(" .,!-")
                if candidate and len(candidate) > 1:  # Ensure it's a valid name
                    self.memory.update_lead_field(conversation_id, "name", candidate)
                    logger.debug(f"Extracted name: {candidate}")

        # Basic phone extraction
        if not lead_data_snapshot.get("phone"):
            phone_match = re.search(r"(\+?\d[\d\s\-]{8,15}\d)", all_user_text)
            if phone_match:
                cleaned = re.sub(r"[^\d+]", "", phone_match.group(1))
                if len(cleaned) >= 10:  # Valid phone number
                    self.memory.update_lead_field(conversation_id, "phone", cleaned)
                    logger.debug(f"Extracted phone: {cleaned}")

        # Basic education detection
        if not lead_data_snapshot.get("education_level"):
            education_map = {
                "matric": "Matric/Intermediate",
                "intermediate": "Matric/Intermediate",
                "o level": "OLevel/Alevel",
                "a level": "OLevel/Alevel",
                "bachelor": "Bachelors",
                "bachelors": "Bachelors",
                "bs ": "Bachelors",
                "master": "Masters",
                "masters": "Masters",
                "mba": "Masters",
                "acca": "Professional",
                "ca ": "Professional",
                "cima": "Professional",
            }
            for keyword, label in education_map.items():
                if keyword in all_user_text_lower:
                    self.memory.update_lead_field(conversation_id, "education_level", label)
                    logger.debug(f"Extracted education: {label}")
                    break

        # Detect course mentions - improved detection
        courses_map = {
            'cta': 'CTA',
            'certified tax advisor': 'CTA',
            'acca': 'ACCA',
            'uk taxation': 'UK_TAXATION',
            'uae taxation': 'UAE_TAXATION',
            'us taxation': 'USA_TAXATION',
            'usa taxation': 'USA_TAXATION',
            'finance': 'FINANCE',
            'accounting': 'ACCOUNTING',
            'company secretary': 'COMPANY_SECRETARY',
            'sales tax': 'SALES_TAX',
        }
        
        # Check all user messages for course mentions
        for course_keyword, course_value in courses_map.items():
            if course_keyword in all_user_text_lower and not self.memory.get_lead_data(conversation_id).get('selected_course'):
                self.memory.update_lead_field(conversation_id, 'selected_course', course_value)
                logger.debug(f"Extracted course: {course_value}")
                break

    def _extract_conversation_text(self, messages: List[BaseMessage]) -> str:
        """Extract conversation text from messages."""
        conversation_parts = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                conversation_parts.append(f"User: {msg.content}")
            elif isinstance(msg, AIMessage):
                # Skip tool calls in the summary
                if not (hasattr(msg, 'tool_calls') and msg.tool_calls):
                    conversation_parts.append(f"Assistant: {msg.content}")
        
        return "\n".join(conversation_parts)
    
    def chat(
        self,
        user_input: str,
        conversation_id: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Process a user message and return the response.
        
        Args:
            user_input: User's message
            conversation_id: Optional conversation ID (creates new if not provided)
            config: Optional LangGraph config
        
        Returns:
            Dictionary with response and metadata
        """
        # Generate or use conversation ID
        if not conversation_id:
            conversation_id = str(uuid.uuid4())
        
        # Prepare config with thread_id for checkpointer
        if config is None:
            config = {
                "configurable": {
                    "thread_id": conversation_id
                }
            }
        
        # Get current turn count from memory (for tracking)
        all_conversation_history = self.memory.get_conversation_history(conversation_id)
        turn_count = len(all_conversation_history)
        
        # IMPORTANT: With LangGraph checkpointer, pass only the new message
        # The checkpointer automatically loads previous state and merges using add_messages reducer
        # This ensures:
        # 1. The checkpointer's memory is properly utilized
        # 2. Previous messages are automatically loaded from checkpointer
        # 3. New message is merged with existing messages
        # 4. The _retrieve_context node will run and get summary + recent history
        initial_state = {
            "messages": [HumanMessage(content=user_input)],  # Only new message - checkpointer handles the rest
            "conversation_id": conversation_id,
            "turn_count": turn_count + 1,
        }
        
        # Run the graph
        # The checkpointer will:
        # 1. Load previous state for this thread_id (if exists)
        # 2. Merge new messages with existing messages (using add_messages reducer)
        # 3. The _retrieve_context node (entry point) will run and populate context
        # 4. The agent node will receive all context (summary + recent messages from checkpointer)
        final_state = self.app.invoke(initial_state, config)
        
        # Extract assistant response
        assistant_messages = [
            msg for msg in final_state["messages"]
            if isinstance(msg, AIMessage) and not (hasattr(msg, 'tool_calls') and msg.tool_calls)
        ]

        assistant_response = assistant_messages[-1].content if assistant_messages else "I apologize, but I couldn't generate a response."

        # Extract and update lead data / stage tracking
        # This must be called BEFORE saving conversation to ensure stage is updated
        self._extract_and_update_lead_data(conversation_id, final_state["messages"])

        # Save conversation to memory (without embedding - production optimization)
        # Only summaries are embedded, not individual turns
        self.memory.add_conversation(
            user_message=user_input,
            assistant_message=assistant_response,
            conversation_id=conversation_id,
            metadata={
                "turn_count": turn_count + 1
            },
            embed=False  # Production: Don't embed individual turns, only summaries
        )
        
        # Get context from final_state (populated by _retrieve_context)
        # Ensure context is always returned, even if empty
        context_used = final_state.get("context", [])
        
        # If context is empty, try to build it from recent history
        # This ensures context is always available in the response
        if not context_used:
            # Fallback: build context from recent history if available
            recent_history = final_state.get("recent_history", [])
            if recent_history:
                context_used = []
                for turn in recent_history:
                    context_used.append({
                        "content": f"User: {turn.get('user_message', '')}\nAssistant: {turn.get('assistant_message', '')}",
                        "metadata": {
                            "conversation_id": conversation_id,
                            "type": "recent_unsummarized_turn",
                            "timestamp": turn.get("timestamp", "")
                        }
                    })
                logger.debug(f"Built context from recent_history: {len(context_used)} items")
            else:
                logger.debug(f"No context available in final_state")
        
        # Get current stage and lead data (after extraction and update)
        current_stage = self.memory.get_stage(conversation_id)
        lead_data = self.memory.get_lead_data(conversation_id)
        
        logger.debug(f"Returning response - stage: {current_stage}, context_count: {len(context_used)}, lead_data: {lead_data}")

        return {
            "response": assistant_response,
            "conversation_id": conversation_id,
            "turn_count": turn_count + 1,
            "context_used": context_used,
            "messages": final_state["messages"],
            "stage": current_stage,
            "lead_data": lead_data
        }
