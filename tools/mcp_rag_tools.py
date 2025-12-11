"""MCP RAG Sheets tool for appending leads data."""
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
        """Append a new lead to the RAG sheets via MCP endpoint.
        
        CRITICAL: Use this tool RIGHT BEFORE sharing demo video link (Step 6 in conversation flow).
        This tool saves lead data to the Leads sheet as specified in the system prompt.
        
        Required fields to capture:
        - Lead_Name: From Step 1 (or "None" if not collected)
        - Selected_Course: From Step 2 (or "None" if not selected)
        - Education_Level: From Step 3 (or "None" if not collected)
        - Goal_Motivation: From Step 4 (or "None" if not collected)
        - Phone_Number: If collected (or "None")
        - Demo_Shared_Date: Current date and time
        - Demo_Link_Sent: "Yes"
        - Conversation_Status: "Demo Shared"
        
        Args:
            name: Lead's name (required) - Use "None" if not collected
            email: Lead's email address (optional)
            phone: Lead's phone number (optional) - Use "None" if not collected
            company: Lead's company name (optional)
            notes: Additional notes about the lead (can include Selected_Course, Education_Level, Goal_Motivation, Demo_Shared_Date, Demo_Link_Sent, Conversation_Status)
            metadata: Additional metadata as key-value pairs (can include course, education, goal, demo_shared_date, etc.)
        
        Returns:
            A confirmation message with the result
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
            return f"Error appending lead: HTTP {e.response.status_code} - {e.response.text}"
        except httpx.RequestError as e:
            return f"Error connecting to MCP endpoint: {str(e)}"
        except Exception as e:
            return f"Error appending lead to RAG sheets: {str(e)}"
    
    return append_lead_to_rag_sheets


def get_mcp_rag_tools() -> List:
    """Get MCP RAG Sheets tools for the agent.
    
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

