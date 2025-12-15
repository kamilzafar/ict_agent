"""MCP RAG Sheets tool for appending leads data and fetching Course_Links."""
import os
import json
from typing import List, Optional, Dict, Any
from langchain_core.tools import tool
from pydantic import BaseModel, Field
import httpx


class LeadDataInput(BaseModel):
    """Input schema for appending lead data."""
    name: str = Field(description="Lead's name")
    email: Optional[str] = Field(default=None, description="Lead's email address")
    phone: Optional[str] = Field(default=None, description="Lead's phone number")
    company: Optional[str] = Field(default=None, description="Lead's company name")
    notes: Optional[str] = Field(default=None, description="Additional notes about the lead")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata as key-value pairs")


def create_mcp_rag_tool():
    """Create an MCP RAG Sheets tool for appending leads.
    
    Returns:
        LangChain tool for appending leads to RAG sheets
    """
    mcp_url = os.getenv("MCP_RAG_SHEETS_URL", "https://www.ictpk.cloud/mcp/rag-sheets")
    
    @tool("append_lead_to_rag_sheets", args_schema=LeadDataInput)
    def append_lead_to_rag_sheets(
        name: str,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        company: Optional[str] = None,
        notes: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Save lead data to Leads sheet. Use ONLY for saving data, NOT for fetching links or course info.
        
        Use this tool right before sharing demo video link (Step 6). Do NOT use for fetching data.
        For links use fetch_course_links, for course info use fetch_course_details.
        
        Args:
            name: Lead name (required, use "None" if not collected)
            email: Email address (optional)
            phone: Phone number (optional, use "None" if not collected)
            company: Company name (optional)
            notes: Additional notes (can include Selected_Course, Education_Level, Goal_Motivation, Demo_Shared_Date, Demo_Link_Sent, Conversation_Status)
            metadata: Additional metadata as key-value pairs
        
        Returns:
            Confirmation message
        """
        try:
            # Prepare lead data
            lead_data = {
                "name": name,
            }
            
            if email:
                lead_data["email"] = email
            if phone:
                lead_data["phone"] = phone
            if company:
                lead_data["company"] = company
            if notes:
                lead_data["notes"] = notes
            if metadata:
                lead_data["metadata"] = metadata
            
            # Call MCP endpoint
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    mcp_url,
                    json=lead_data,
                    headers={
                        "Content-Type": "application/json",
                    }
                )
                response.raise_for_status()
                
                result = response.json() if response.headers.get("content-type", "").startswith("application/json") else {"status": "success"}
                
                return f"Successfully appended lead '{name}' to RAG sheets. Response: {json.dumps(result, indent=2)}"
        
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 406:
                return f"Error: HTTP 406 Not Acceptable. The MCP endpoint rejected the request. This tool is ONLY for saving lead data - if you need to fetch links or course data, use fetch_course_links or fetch_course_details instead."
            return f"Error appending lead: HTTP {e.response.status_code} - {e.response.text}"
        except httpx.RequestError as e:
            return f"Error connecting to MCP endpoint: {str(e)}"
        except Exception as e:
            return f"Error appending lead to RAG sheets: {str(e)}"
    
    return append_lead_to_rag_sheets


def get_mcp_rag_tools(sheets_cache_service=None) -> List:
    """Get MCP RAG Sheets tools for the agent.
    
    Args:
        sheets_cache_service: Optional Google Sheets cache service instance
    
    Returns:
        List of MCP RAG tools
    """
    tools = []
    
    try:
        # Always create the tool (MCP URL can be configured via env var)
        append_tool = create_mcp_rag_tool()
        tools.append(append_tool)
    except Exception as e:
        import logging
        logging.warning(f"Could not initialize MCP RAG tools: {e}")
    
    return tools

