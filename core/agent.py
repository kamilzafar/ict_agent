"""LangGraph agent with long-term memory and summarization."""
import os
import re
import uuid
from typing import Annotated, TypedDict, List, Dict, Any, Optional, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    from core.sheets_cache import GoogleSheetsCacheService

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

from core.memory import LongTermMemory
from tools.mcp_rag_tools import get_mcp_rag_tools
from tools.sheets_tools import create_google_sheets_tools
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
        memory_db_path: str = "./memory_db",
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
        
        # Get available tools (MCP RAG tools + Google Sheets tools)
        self.mcp_rag_tools = get_mcp_rag_tools(sheets_cache_service)
        self.sheets_tools = create_google_sheets_tools(sheets_cache_service) if sheets_cache_service else []
        
        # Combine all tools
        all_tools = self.mcp_rag_tools + self.sheets_tools
        
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
        """Retrieve relevant context from long-term memory."""
        messages = state["messages"]
        
        # Get the last user message
        user_message = None
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                user_message = msg.content
                break
        
        if user_message:
            conversation_id = state.get("conversation_id")
            
            # Search for relevant context from summaries (cached, only searches summaries)
            relevant_docs = self.memory.search_relevant_context(
                query=user_message,
                k=3,  # Reduced from 5 for efficiency
                conversation_id=conversation_id,
                use_cache=True  # Use cache to avoid redundant searches
            )
            
            # Format context (limit to prevent token overflow)
            context_texts = []
            for doc in relevant_docs[:3]:  # Max 3 summaries
                context_texts.append(f"[Previous conversation summary]: {doc.page_content}")
            
            # Also get conversation summary for current conversation if available
            if conversation_id:
                current_summary = self.memory.get_conversation_summary(conversation_id)
                if current_summary:
                    # Check if summary is not already in context_texts
                    summary_already_included = any(current_summary in text for text in context_texts)
                    if not summary_already_included:
                        context_texts.insert(0, f"[Current conversation summary]: {current_summary}")
            
            if context_texts:
                # Store context in state for use in system prompt
                # Don't add as SystemMessage here as it will be filtered out
                state["context"] = [{"content": doc.page_content, "metadata": doc.metadata} 
                                   for doc in relevant_docs[:3]]
                # Store formatted context text for system prompt
                state["retrieved_context"] = "\n\n".join(context_texts)
        
        return state
    
    def _call_agent(self, state: AgentState) -> AgentState:
        """Call the agent LLM."""
        messages = state["messages"]
        
        # Create system prompt
        system_prompt = self._get_system_prompt(state)
        system_message = SystemMessage(content=system_prompt)
        
        # Prepare messages with system prompt
        # The system prompt already includes the conversation summary (all summarized turns)
        # We only need to include the most recent messages that haven't been summarized
        agent_messages = [system_message]
        
        # Filter out system messages (they're already in the system prompt)
        # Keep only conversation messages (HumanMessage and AIMessage)
        # These should only be the unsummarized turns (loaded in chat method)
        conversation_messages = [
            msg for msg in messages 
            if not isinstance(msg, SystemMessage)
        ]
        
        # Add all conversation messages (they're already limited to unsummarized turns)
        # The chat() method ensures we only load turns that haven't been summarized
        agent_messages.extend(conversation_messages)
        
        # Call LLM
        response = self.llm_with_tools.invoke(agent_messages)
        
        # Add response to messages
        state["messages"].append(response)
        
        return state
    
    def _get_system_prompt(self, state: AgentState) -> str:
        """Get the system prompt for the agent."""
        conversation_id = state.get("conversation_id", "unknown")
        turn_count = state.get("turn_count", 0)
        
        # Get conversation summary if available
        summary = self.memory.get_conversation_summary(conversation_id)
        summary_text = f"\n\nConversation Summary: {summary}" if summary else ""
        
        # Add retrieved context if available (from _retrieve_context)
        retrieved_context = state.get("retrieved_context", "")
        context_text = f"\n\nRetrieved Context from Previous Conversations:\n{retrieved_context}" if retrieved_context else ""
        
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
        
        # Add conversation context
        context_info = f"""
## CURRENT CONVERSATION CONTEXT:
- Conversation ID: {conversation_id}
- Turn Count: {turn_count}
{summary_text}
"""
        
        # Combine prompt with context
        full_prompt = base_prompt + tool_info + context_info + context_text + sheets_context
        
        return full_prompt
    
    def _should_continue(self, state: AgentState) -> str:
        """Determine if we should continue (call tools), summarize, or end."""
        messages = state["messages"]
        last_message = messages[-1]
        
        # If the last message has tool calls, continue to tools
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            return "continue"
        
        # Check if we should summarize (every N turns)
        turn_count = state.get("turn_count", 0)
        if turn_count > 0 and turn_count % self.summarize_interval == 0:
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
        
        # Remove the summarized messages from state
        # Keep system messages and any messages before the ones we're summarizing
        system_messages = [msg for msg in messages if isinstance(msg, SystemMessage)]
        
        # Remove the last N conversation messages (the ones we just summarized)
        messages_to_keep = conversation_messages[:-self.summarize_interval]
        
        # Reconstruct state with only kept messages + system messages
        state["messages"] = system_messages + messages_to_keep

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
        user_text = ""
        for msg in messages:
            if isinstance(msg, HumanMessage) and hasattr(msg, "content"):
                user_text += msg.content + " "

        user_text_lower = user_text.lower()

        # Basic name extraction when tool data is not available
        if not lead_data_snapshot.get("name"):
            name_match = re.search(r"(?:my name is|i am|i'm|this is)\s+([A-Za-z][A-Za-z\s]{1,40})", user_text, re.IGNORECASE)
            if name_match:
                candidate = name_match.group(1).strip(" .,!-")
                if candidate:
                    self.memory.update_lead_field(conversation_id, "name", candidate)

        # Basic phone extraction
        if not lead_data_snapshot.get("phone"):
            phone_match = re.search(r"(\+?\d[\d\s\-]{8,15}\d)", user_text)
            if phone_match:
                cleaned = re.sub(r"[^\d+]", "", phone_match.group(1))
                self.memory.update_lead_field(conversation_id, "phone", cleaned)

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
                if keyword in user_text_lower:
                    self.memory.update_lead_field(conversation_id, "education_level", label)
                    break

        # Detect course mentions
        courses = ['cta', 'acca', 'uk taxation', 'uae taxation', 'us taxation', 'finance', 'accounting']
        for course in courses:
            if course in user_text_lower and not self.memory.get_lead_data(conversation_id).get('selected_course'):
                self.memory.update_lead_field(conversation_id, 'selected_course', course.upper())
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
        
        # Get current turn count and conversation history
        all_conversation_history = self.memory.get_conversation_history(conversation_id)
        turn_count = len(all_conversation_history)
        
        # Calculate which turns have been summarized
        # After summarization, we should only load the most recent turns that haven't been summarized
        # Example: If summarize_interval=10:
        #   - Turns 1-10: All loaded (no summarization yet)
        #   - Turn 11: Only turn 11 loaded (turns 1-10 are summarized)
        #   - Turns 11-20: Only turns 11-20 loaded (turns 1-10 are summarized)
        #   - Turn 21: Only turn 21 loaded (turns 1-20 are summarized)
        
        if turn_count > 0:
            # Calculate how many complete summarization cycles have occurred
            num_complete_cycles = turn_count // self.summarize_interval
            
            if num_complete_cycles > 0:
                # We've had at least one summarization
                # Only load the most recent turns that haven't been summarized yet
                turns_since_last_summary = turn_count % self.summarize_interval
                
                if turns_since_last_summary == 0:
                    # Exactly at a summarization point (e.g., turn 10, 20, 30)
                    # Load the last summarize_interval turns (they will be summarized in this turn)
                    # These are the turns since the last summarization
                    conversation_history = all_conversation_history[-self.summarize_interval:]
                else:
                    # Load only the most recent turns that haven't been summarized
                    # These are the turns since the last summarization
                    conversation_history = all_conversation_history[-turns_since_last_summary:]
            else:
                # No summarization yet, load all turns (they're all recent)
                conversation_history = all_conversation_history
        else:
            conversation_history = []
        
        # Load previous conversation history into messages
        # This ensures the agent has context from previous turns that haven't been summarized
        previous_messages = []
        for turn in conversation_history:
            # Add user message
            previous_messages.append(HumanMessage(content=turn.get("user_message", "")))
            # Add assistant message
            previous_messages.append(AIMessage(content=turn.get("assistant_message", "")))
        
        # Create initial state with previous messages + current user message
        initial_state = {
            "messages": previous_messages + [HumanMessage(content=user_input)],
            "conversation_id": conversation_id,
            "turn_count": turn_count + 1,
            "context": [],
            "retrieved_context": ""  # Will be populated by _retrieve_context
        }
        
        # Prepare config
        if config is None:
            config = {
                "configurable": {
                    "thread_id": conversation_id
                }
            }
        
        # Run the graph
        final_state = self.app.invoke(initial_state, config)
        
        # Extract assistant response
        assistant_messages = [
            msg for msg in final_state["messages"]
            if isinstance(msg, AIMessage) and not (hasattr(msg, 'tool_calls') and msg.tool_calls)
        ]

        assistant_response = assistant_messages[-1].content if assistant_messages else "I apologize, but I couldn't generate a response."

        # Extract and update lead data / stage tracking
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
        
        # Get current stage and lead data
        current_stage = self.memory.get_stage(conversation_id)
        lead_data = self.memory.get_lead_data(conversation_id)

        return {
            "response": assistant_response,
            "conversation_id": conversation_id,
            "turn_count": turn_count + 1,
            "context_used": final_state.get("context", []),
            "messages": final_state["messages"],
            "stage": current_stage,
            "lead_data": lead_data
        }
