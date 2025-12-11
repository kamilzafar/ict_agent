"""LangGraph agent with long-term memory and summarization."""
import os
import uuid
from typing import Annotated, TypedDict, List, Dict, Any, Optional
from datetime import datetime

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

from core.memory import LongTermMemory
from tools.pinecone_tools import get_pinecone_tools
from tools.mcp_rag_tools import get_mcp_rag_tools


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
        model_name: str = "gpt-4o",  # Changed to gpt-4o for 128k context window
        temperature: float = 0.7,
        memory_db_path: str = "./memory_db",
        summarize_interval: int = 10
    ):
        """Initialize the agent.
        
        Args:
            model_name: Name of the LLM model to use
            temperature: Temperature for the LLM
            memory_db_path: Path to the memory database
            summarize_interval: Number of turns before summarizing
        """
        self.memory = LongTermMemory(persist_directory=memory_db_path)
        self.summarize_interval = summarize_interval
        
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
        
        # Get all available tools
        self.pinecone_tools = get_pinecone_tools()
        self.mcp_rag_tools = get_mcp_rag_tools()
        
        # Combine all tools
        all_tools = self.pinecone_tools + self.mcp_rag_tools
        
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
            # Search for relevant context (cached, only searches summaries)
            relevant_docs = self.memory.search_relevant_context(
                query=user_message,
                k=3,  # Reduced from 5 for efficiency
                conversation_id=state.get("conversation_id"),
                use_cache=True  # Use cache to avoid redundant searches
            )
            
            # Format context (limit to prevent token overflow)
            context_texts = []
            for doc in relevant_docs[:3]:  # Max 3 summaries
                context_texts.append(f"[Previous conversation]: {doc.page_content}")
            
            if context_texts:
                context_message = SystemMessage(
                    content=f"Relevant context from previous conversations:\n\n" + 
                           "\n\n".join(context_texts)
                )
                state["messages"].append(context_message)
                state["context"] = [{"content": doc.page_content, "metadata": doc.metadata} 
                                   for doc in relevant_docs[:3]]
        
        return state
    
    def _call_agent(self, state: AgentState) -> AgentState:
        """Call the agent LLM."""
        messages = state["messages"]
        
        # Create system prompt
        system_prompt = self._get_system_prompt(state)
        system_message = SystemMessage(content=system_prompt)
        
        # Prepare messages with system prompt
        # Only include system prompt if it's not already in the messages
        # Limit conversation history to prevent context overflow (gpt-4o has 128k, but be safe)
        agent_messages = [system_message]
        
        # Limit to last 30 messages to manage context (with 128k tokens, this should be safe)
        # Filter out any existing system messages to avoid duplication
        conversation_messages = [
            msg for msg in messages 
            if not isinstance(msg, SystemMessage)
        ]
        
        if len(conversation_messages) > 30:
            agent_messages.extend(conversation_messages[-30:])
        else:
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
        
        # Load system prompt from file
        prompt_file = os.path.join(os.path.dirname(__file__), "..", "config", "prompt.txt")
        prompt_file = os.path.normpath(prompt_file)  # Normalize path for cross-platform compatibility
        try:
            with open(prompt_file, "r", encoding="utf-8") as f:
                base_prompt = f.read()
        except FileNotFoundError:
            # Fallback if prompt.txt doesn't exist
            base_prompt = """You are Tanveer Awan, an Enrollment Advisor at Institute of Corporate & Taxation (ICT).
You are a real human - not an AI. Never break character.
You help leads with course enrollment through WhatsApp conversations."""
        
        # Add tool information
        tool_info = ""
        if self.all_tools:
            tool_descriptions = []
            if self.pinecone_tools:
                tool_descriptions.append("a vector database search tool (search_vector_database) - Use this to retrieve information from Google Sheets or knowledge base when you need course data, links, fees, dates, professor info, FAQs, or any information")
            if self.mcp_rag_tools:
                tool_descriptions.append("a tool to append lead data to RAG sheets (append_lead_to_rag_sheets) - Use this to save lead information when collecting data or before sharing demo video link")
            
            if tool_descriptions:
                tool_info = f"\n\n## AVAILABLE TOOLS:\n\nYou have access to the following tools:\n"
                for desc in tool_descriptions:
                    tool_info += f"- {desc}\n"
                tool_info += "\nIMPORTANT: Always use the search_vector_database tool to fetch data from Google Sheets before sharing any course information, links, fees, dates, or other data.\n"
                tool_info += "Use append_lead_to_rag_sheets tool to save lead data before sharing demo video link (Step 6).\n"
        
        # Add conversation context
        context_info = f"""
## CURRENT CONVERSATION CONTEXT:
- Conversation ID: {conversation_id}
- Turn Count: {turn_count}
{summary_text}
"""
        
        # Combine prompt
        full_prompt = base_prompt + tool_info + context_info
        
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
        
        # Get current turn count
        conversation_history = self.memory.get_conversation_history(conversation_id)
        turn_count = len(conversation_history)
        
        # Create initial state
        initial_state = {
            "messages": [HumanMessage(content=user_input)],
            "conversation_id": conversation_id,
            "turn_count": turn_count + 1,
            "context": []
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
        
        return {
            "response": assistant_response,
            "conversation_id": conversation_id,
            "turn_count": turn_count + 1,
            "context_used": final_state.get("context", []),
            "messages": final_state["messages"]
        }

