"""LangGraph agent with long-term memory and summarization."""
import os
import re
import uuid
import logging
from typing import Annotated, TypedDict, List, Dict, Any, Optional, TYPE_CHECKING
from datetime import datetime

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.supabase_service import SupabaseService

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage, trim_messages
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
try:
    from langgraph.checkpoint.sqlite import SqliteSaver
    SQLITE_CHECKPOINTER_AVAILABLE = True
except ImportError:
    SQLITE_CHECKPOINTER_AVAILABLE = False
    from langgraph.checkpoint.memory import MemorySaver
    logger.warning("SQLite checkpointer not available. Install with: pip install langgraph-checkpoint-sqlite")

from core.memory import LongTermMemory
from tools.supabase_tools import create_supabase_tools
from tools.template_tools import template_tools
from core.context_injector import ContextInjector

# Cache removed - all calls go directly to database/API


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
        model_name: str = "gpt-4.1-mini",  # GPT-4.1 Mini with 128k context window
        temperature: float = 0.7,
        memory_db_path: str = "/app/memory_db",
        summarize_interval: int = 10,
        recursion_limit: int = 50,
        supabase_service: Optional[Any] = None
    ):
        """Initialize the agent.

        Args:
            model_name: Name of the LLM model to use
            temperature: Temperature for the LLM
            memory_db_path: Path to the memory database
            summarize_interval: Number of turns before summarizing
            recursion_limit: Maximum graph recursion depth (default: 50)
            supabase_service: Optional SupabaseService instance
        """
        self.model_name = model_name
        self.temperature = temperature
        self.memory = LongTermMemory(persist_directory=memory_db_path)
        self.summarize_interval = summarize_interval
        self.recursion_limit = recursion_limit
        
        # Initialize context injector if Supabase service is provided
        self.context_injector = None
        if supabase_service:
            self.context_injector = ContextInjector(supabase_service)
        
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
        
        # No caching - all LLM calls go directly to OpenAI API
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
        
        # Get available tools (Supabase tools + Sheets tools + Template tools)
        # All tool creation functions are production-safe (return empty list on failure)
        try:
            self.supabase_tools = create_supabase_tools(supabase_service) if supabase_service else []
            logger.debug(f"Created {len(self.supabase_tools)} Supabase tools")
        except Exception as e:
            logger.warning(f"Error creating Supabase tools: {e}")
            self.supabase_tools = []
        
        try:
            self.template_tools = template_tools  # Always available
            logger.debug(f"Created {len(self.template_tools)} template tools")
        except Exception as e:
            logger.warning(f"Error loading template tools: {e}")
            self.template_tools = []

        # Combine all tools (Supabase now includes lead data append)
        all_tools = self.supabase_tools + self.template_tools
        logger.info(f"✓ Total tools available: {len(all_tools)} (Supabase: {len(self.supabase_tools)} [includes lead data], Templates: {len(self.template_tools)})")
        
        # Bind tools to LLM if available
        if all_tools:
            self.llm_with_tools = self.llm.bind_tools(all_tools)
        else:
            self.llm_with_tools = self.llm
        
        # Store tools for graph creation
        self.all_tools = all_tools
        
        # Create the graph
        self.graph = self._create_graph()
        
        # Compile the graph with persistent checkpointer
        # Use SQLite for production persistence, fallback to MemorySaver if not available
        try:
            if SQLITE_CHECKPOINTER_AVAILABLE:
                checkpoint_db = os.path.join(memory_db_path, "checkpoints.db")
                os.makedirs(memory_db_path, exist_ok=True)

                # Ensure directory is writable (critical for Docker)
                if not os.access(memory_db_path, os.W_OK):
                    logger.warning(f"Memory DB path not writable: {memory_db_path}")
                    try:
                        os.chmod(memory_db_path, 0o777)
                    except Exception as perm_error:
                        logger.error(f"Cannot fix permissions: {perm_error}")

                # Create SQLite connection directly (don't use context manager for long-running instance)
                # Use absolute path for Windows compatibility
                checkpoint_db_abs = os.path.abspath(checkpoint_db)
                import sqlite3
                conn = sqlite3.connect(
                    checkpoint_db_abs,
                    check_same_thread=False  # Thread-safe with lock in SqliteSaver
                )
                self.checkpointer = SqliteSaver(conn)
                logger.info(f"✓ SQLite checkpointer initialized: {checkpoint_db_abs}")

                # Verify database file was created
                if os.path.exists(checkpoint_db_abs):
                    file_size = os.path.getsize(checkpoint_db_abs)
                    logger.debug(f"Checkpoint database file created: {file_size} bytes")
                else:
                    logger.warning(f"Checkpoint database file not found: {checkpoint_db_abs}")
            else:
                self.checkpointer = MemorySaver()
                logger.warning("Using in-memory checkpointer (not persistent). Install langgraph-checkpoint-sqlite for persistence.")
        except Exception as e:
            logger.error(f"Error initializing checkpointer: {e}", exc_info=True)
            logger.warning("Falling back to in-memory checkpointer")
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
        
        # Filter out only system messages (keep all conversation messages including ToolMessages)
        # We need to keep ToolMessages because OpenAI API requires them to follow AIMessages with tool_calls
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

        # Validate and clean message sequence to prevent OpenAI API errors
        # Build list of valid tool_call_ids (from AIMessages that will be kept)
        valid_tool_call_ids = set()
        messages_to_remove = set()

        # First pass: identify AIMessages with tool_calls and track their IDs
        for i, msg in enumerate(conversation_messages):
            if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and msg.tool_calls:
                tool_call_ids = [tc['id'] for tc in msg.tool_calls]

                # Check if all corresponding ToolMessages exist after this AIMessage
                following_tool_msgs = {}
                for j in range(i+1, len(conversation_messages)):
                    if isinstance(conversation_messages[j], ToolMessage):
                        following_tool_msgs[conversation_messages[j].tool_call_id] = j
                    elif not isinstance(conversation_messages[j], ToolMessage):
                        # Stop looking after we hit a non-ToolMessage
                        break

                # If we don't have ToolMessages for ALL tool_calls, remove this AIMessage
                missing_responses = [tcid for tcid in tool_call_ids if tcid not in following_tool_msgs]
                if missing_responses:
                    logger.warning(f"AIMessage at {i} has tool_calls {tool_call_ids} but missing ToolMessages for {missing_responses}")
                    logger.warning(f"Removing AIMessage at position {i} and its partial ToolMessages to prevent API error")
                    messages_to_remove.add(i)
                    # Also remove the ToolMessages that DO exist for this AIMessage
                    for tcid, idx in following_tool_msgs.items():
                        messages_to_remove.add(idx)
                else:
                    # All ToolMessages present, mark these tool_call_ids as valid
                    valid_tool_call_ids.update(tool_call_ids)

        # Second pass: remove orphaned ToolMessages (ToolMessages without corresponding AIMessage)
        for i, msg in enumerate(conversation_messages):
            if isinstance(msg, ToolMessage):
                if msg.tool_call_id not in valid_tool_call_ids:
                    logger.warning(f"Orphaned ToolMessage at {i} with tool_call_id={msg.tool_call_id}, removing")
                    messages_to_remove.add(i)

        # Remove marked messages
        conversation_messages = [msg for i, msg in enumerate(conversation_messages) if i not in messages_to_remove]

        if messages_to_remove:
            logger.info(f"Removed {len(messages_to_remove)} messages to maintain valid tool call sequence")
        
        # Prepare final messages following LangChain best practices:
        # 1. System prompt (base instructions, tools, metadata - NO summary)
        # 2. Summary as context memory (injected as message)
        # 3. All unsummarized messages (actual conversation, NO ToolMessage objects)
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

            # Supabase tools (for fetching data and saving leads)
            if self.supabase_tools:
                tool_descriptions.append("fetch_course_links - always use this tool to Get demo links, PDF links, or course page links from database")
                tool_descriptions.append("fetch_course_details - always use this tool to Get course information (fees, duration, dates, professor, locations) from database")
                tool_descriptions.append("fetch_faqs - always use this tool to Get FAQs from database")
                tool_descriptions.append("fetch_professor_info - always use this tool to Get professor/trainer information from database")
                tool_descriptions.append("fetch_company_info - always use this tool to Get company information (contact, social media, locations) from database")
                tool_descriptions.append("append_lead_data - always use this tool to Save/Update lead data in Supabase (UPSERT - MANDATORY before sharing demo link)")

            if tool_descriptions:
                tool_info = f"\n\n## AVAILABLE TOOLS:\n\nYou have access to the following tools:\n"
                for desc in tool_descriptions:
                    tool_info += f"- {desc}\n"
                tool_info += "\nIMPORTANT TOOL USAGE RULES:\n"
                tool_info += "- Always use this tool To GET links (demo, PDF, course page) → Use fetch_course_links\n"
                tool_info += "- Always use this tool To GET course information → Use fetch_course_details\n"
                tool_info += "- Always use this tool To GET FAQs → Use fetch_faqs\n"
                tool_info += "- Always use this tool To GET professor info → Use fetch_professor_info\n"
                tool_info += "- Always use this tool To GET company info → Use fetch_company_info\n"
                tool_info += "- Always use this tool To SAVE lead data to Supabase (before demo link) → Use append_lead_data (MANDATORY)\n"
        
        # Add conversation metadata
        context_info = f"""
## CURRENT CONVERSATION METADATA:
- Conversation ID: {conversation_id}
- Turn Count: {turn_count}
- Note: Conversation summary is provided as context memory (not in this system prompt)
"""
        
        # Combine prompt (NO summary here - it's injected as context memory)
        full_prompt = base_prompt + tool_info + context_info
        
        return full_prompt
    
    def _should_continue(self, state: AgentState) -> str:
        """Determine if we should continue (call tools), summarize, or end.

        SAFETY MECHANISMS:
        1. Tool call counter - prevent infinite loops
        2. Duplicate tool detection - avoid redundant calls
        3. Maximum iterations per turn - hard limit
        """
        messages = state["messages"]
        last_message = messages[-1]

        # SAFETY CHECK 1: Count tool calls in this conversation turn
        # Prevent infinite loops by limiting tool calls per user message
        tool_call_count = 0
        ai_message_count = 0

        # Count from the last HumanMessage (current turn)
        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            if isinstance(msg, HumanMessage):
                break  # Stop at last user message (start of current turn)
            if isinstance(msg, AIMessage):
                ai_message_count += 1
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    tool_call_count += len(msg.tool_calls)

        # SAFETY CHECK 2: Hard limit on tool calls per turn (scalability)
        MAX_TOOL_CALLS_PER_TURN = 10  # Reasonable limit for most queries
        MAX_AI_ITERATIONS = 6  # Maximum agent->tools->agent cycles

        if tool_call_count >= MAX_TOOL_CALLS_PER_TURN:
            logger.warning(
                f"⚠️ SAFETY STOP: Reached max tool calls ({tool_call_count}/{MAX_TOOL_CALLS_PER_TURN}) "
                f"for current turn. Forcing end to prevent infinite loop."
            )
            return "end"

        if ai_message_count >= MAX_AI_ITERATIONS:
            logger.warning(
                f"⚠️ SAFETY STOP: Reached max AI iterations ({ai_message_count}/{MAX_AI_ITERATIONS}) "
                f"for current turn. Forcing end to prevent infinite loop."
            )
            return "end"

        # SAFETY CHECK 3: Detect duplicate tool calls (same tool with same args)
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            # Check if we're about to make a duplicate call
            for new_call in last_message.tool_calls:
                for i in range(len(messages) - 2, -1, -1):  # Check previous messages
                    msg = messages[i]
                    if isinstance(msg, HumanMessage):
                        break  # Stop at last user message
                    if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and msg.tool_calls:
                        for prev_call in msg.tool_calls:
                            # Check if same tool with same arguments
                            if (prev_call.get('name') == new_call.get('name') and
                                prev_call.get('args') == new_call.get('args')):
                                logger.warning(
                                    f"⚠️ DUPLICATE TOOL CALL DETECTED: {new_call.get('name')} "
                                    f"with same args. This might indicate a loop."
                                )
                                # Still allow it, but log for monitoring

            # Log tool usage for monitoring
            tool_names = [tc.get('name') for tc in last_message.tool_calls]
            logger.info(
                f"Tool calls requested: {tool_names} "
                f"(total this turn: {tool_call_count + len(last_message.tool_calls)}/{MAX_TOOL_CALLS_PER_TURN})"
            )

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
        logger.debug(f"Turn complete: {tool_call_count} tools used, {ai_message_count} AI iterations")
        return "end"
    
    def _summarize_conversation(self, state: AgentState) -> AgentState:
        """Summarize the last N messages and remove them from state."""
        conversation_id = state.get("conversation_id")
        messages = state["messages"]
        
        if not conversation_id:
            return state
        
        # Filter out system messages and ToolMessages (keep AIMessages even if they have tool_calls)
        # We want to summarize the conversation flow, including when AI used tools
        # ToolMessages are internal responses and don't need to be in the summary
        conversation_messages = [
            msg for msg in messages
            if not isinstance(msg, SystemMessage)
            and not isinstance(msg, ToolMessage)
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

        # Check for tool calls and extract lead data
        for message in messages:
            if hasattr(message, 'tool_calls') and message.tool_calls:
                for tool_call in message.tool_calls:
                    # Extract lead data from any tool call arguments if present
                    args = tool_call.get('args', {})

                    if args.get('name'):
                        self.memory.update_lead_field(conversation_id, 'name', args['name'])

                    if args.get('phone'):
                        self.memory.update_lead_field(conversation_id, 'phone', args['phone'])

                        # Extract other data from notes or metadata
                        # Handle None case: if notes is None or missing, use empty string
                        notes = args.get('notes') or ''
                        # Ensure metadata is always a dict
                        metadata = args.get('metadata') or {}

                        # Try to extract course from notes or metadata
                        if notes and 'Selected_Course:' in notes:
                            try:
                                course = notes.split('Selected_Course:')[1].split(',')[0].strip()
                                if course:
                                    self.memory.update_lead_field(conversation_id, 'selected_course', course)
                            except (IndexError, AttributeError):
                                logger.debug(f"Could not extract course from notes: {notes[:50]}")
                        elif metadata.get('course'):
                            self.memory.update_lead_field(conversation_id, 'selected_course', metadata['course'])

                        # Try to extract education level
                        if notes and 'Education_Level:' in notes:
                            try:
                                education = notes.split('Education_Level:')[1].split(',')[0].strip()
                                if education:
                                    self.memory.update_lead_field(conversation_id, 'education_level', education)
                            except (IndexError, AttributeError):
                                logger.debug(f"Could not extract education from notes: {notes[:50]}")
                        elif metadata.get('education'):
                            self.memory.update_lead_field(conversation_id, 'education_level', metadata['education'])

                        # Try to extract goal
                        if notes and 'Goal_Motivation:' in notes:
                            try:
                                goal = notes.split('Goal_Motivation:')[1].split(',')[0].strip()
                                if goal:
                                    self.memory.update_lead_field(conversation_id, 'goal', goal)
                            except (IndexError, AttributeError):
                                logger.debug(f"Could not extract goal from notes: {notes[:50]}")
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
        
        # Prepare config with thread_id for checkpointer and recursion_limit
        if config is None:
            config = {
                "configurable": {
                    "thread_id": conversation_id
                },
                "recursion_limit": self.recursion_limit  # Increased from default 25 to handle multiple tool calls
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
        try:
            final_state = self.app.invoke(initial_state, config)
        except Exception as e:
            logger.error(f"Error running graph for conversation {conversation_id}: {e}", exc_info=True)
            # Fallback: Ensure conversation history exists in LongTermMemory
            all_history = self.memory.get_conversation_history(conversation_id)
            if all_history:
                logger.warning("Graph execution failed, but conversation history exists in LongTermMemory")
            raise RuntimeError(f"Failed to process message: {str(e)}") from e
        
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
