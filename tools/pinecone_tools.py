"""Pinecone vector database tools for LangChain."""
import os
from typing import List, Optional
from langchain_core.tools import tool
from langchain_core.documents import Document
from langchain_pinecone import PineconeVectorStore
from langchain_openai import OpenAIEmbeddings
from pydantic import BaseModel, Field


class VectorSearchInput(BaseModel):
    """Input schema for vector search tool."""
    query: str = Field(description="The search query to find relevant information")
    top_k: int = Field(default=5, description="Number of results to return (default: 5)")
    namespace: Optional[str] = Field(default=None, description="Optional namespace to search in")


def create_pinecone_tool(
    index_name: Optional[str] = None,
    namespace: Optional[str] = None
):
    """Create a Pinecone vector search tool.
    
    Args:
        index_name: Name of the Pinecone index (defaults to env var)
        namespace: Default namespace to search in
    
    Returns:
        LangChain tool for Pinecone search
    """
    # Get Pinecone configuration from environment
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        raise ValueError(
            "PINECONE_API_KEY environment variable is required for Pinecone tools. "
            "Set it in your .env file or environment variables."
        )
    
    if not index_name:
        index_name = os.getenv("PINECONE_INDEX_NAME", "default-index")
    
    # Initialize embeddings with OpenAI small model (512 dimensions)
    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",
        dimensions=512
    )
    
    # Initialize Pinecone vector store
    vectorstore = PineconeVectorStore(
        index_name=index_name,
        embedding=embeddings,
        namespace=namespace
    )
    
    @tool("search_vector_database", args_schema=VectorSearchInput)
    def search_vector_database(query: str, top_k: int = 5, namespace: Optional[str] = None) -> str:
        """Search the vector database (Google Sheets via MCP) for relevant information.
        
        CRITICAL: You MUST use this tool to fetch ALL data from Google Sheets. NEVER use memory or cached data.
        
        Use this tool for:
        - Course fees, batch dates, professor names (from Course_Details sheet)
        - Demo video links, PDF links, course links (from Course_Links sheet)
        - Course duration, locations, prerequisites (from Course_Details sheet)
        - Policy information, FAQs (from FAQs sheet)
        - Instructor information (from About_Profr sheet)
        - General company info (from Company_Info sheet)
        - Chat history for returning leads (from Vector Store)
        
        MANDATORY: Fetch from sheets even if you think you remember the data.
        
        Args:
            query: The search query to find relevant information (e.g., "CTA course fee", "UAE Taxation demo link", "professor name for UK Taxation")
            top_k: Number of results to return (default: 5)
            namespace: Optional namespace to search in
        
        Returns:
            A formatted string with the search results from Google Sheets
        """
        try:
            # Perform similarity search
            if namespace:
                # Create a new vectorstore instance with the namespace
                search_store = PineconeVectorStore(
                    index_name=index_name,
                    embedding=OpenAIEmbeddings(
                        model="text-embedding-3-small",
                        dimensions=512
                    ),
                    namespace=namespace
                )
                results = search_store.similarity_search(query, k=top_k)
            else:
                results = vectorstore.similarity_search(query, k=top_k)
            
            if not results:
                return f"No relevant information found for query: '{query}'"
            
            # Format results
            formatted_results = []
            for i, doc in enumerate(results, 1):
                content = doc.page_content
                metadata = doc.metadata
                
                result_text = f"[Result {i}]:\n{content}"
                if metadata:
                    metadata_str = ", ".join([f"{k}: {v}" for k, v in metadata.items()])
                    result_text += f"\n(Metadata: {metadata_str})"
                
                formatted_results.append(result_text)
            
            return "\n\n".join(formatted_results)
        
        except Exception as e:
            return f"Error searching vector database: {str(e)}"
    
    return search_vector_database


def get_pinecone_tools(index_name: Optional[str] = None) -> List:
    """Get Pinecone tools for the agent.
    
    Args:
        index_name: Name of the Pinecone index
    
    Returns:
        List of Pinecone tools
    """
    tools = []
    
    try:
        # Check if Pinecone is configured
        if os.getenv("PINECONE_API_KEY"):
            search_tool = create_pinecone_tool(index_name=index_name)
            tools.append(search_tool)
        else:
            print("Warning: PINECONE_API_KEY not set. Pinecone tools will not be available.")
    except Exception as e:
        print(f"Warning: Could not initialize Pinecone tools: {e}")
    
    return tools

