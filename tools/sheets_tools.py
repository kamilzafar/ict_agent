"""Google Sheets tools for LangChain agents - appending lead data."""
import os
import logging
from typing import List, Optional
from datetime import datetime
from langchain_core.tools import tool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

try:
    import gspread
    from google.oauth2.service_account import Credentials
    SHEETS_AVAILABLE = True
except ImportError:
    SHEETS_AVAILABLE = False
    logger.warning("Google Sheets libraries not installed. Install with: pip install gspread google-auth")


class AppendLeadDataInput(BaseModel):
    """Input schema for appending lead data to Google Sheets."""
    name: Optional[str] = Field(default="None", description="Lead name")
    selected_course: Optional[str] = Field(default="None", description="Selected course name")
    education_level: Optional[str] = Field(default="None", description="Education level")
    goal: Optional[str] = Field(default="None", description="Goal or motivation")
    phone: Optional[str] = Field(default="None", description="Phone number")
    notes: Optional[str] = Field(default="", description="Additional notes")


def _get_sheets_client():
    """Get authenticated Google Sheets client."""
    if not SHEETS_AVAILABLE:
        raise ImportError("Google Sheets libraries not installed. Install with: pip install gspread google-auth")
    
    credentials_path = os.getenv("GOOGLE_SHEETS_CREDENTIALS_PATH")
    if not credentials_path:
        raise ValueError("GOOGLE_SHEETS_CREDENTIALS_PATH environment variable not set")
    
    if not os.path.exists(credentials_path):
        raise FileNotFoundError(f"Credentials file not found: {credentials_path}")
    
    spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    if not spreadsheet_id:
        raise ValueError("GOOGLE_SHEETS_SPREADSHEET_ID environment variable not set")
    
    sheet_name = os.getenv("GOOGLE_SHEETS_LEADS_SHEET_NAME", "Leads")
    
    try:
        creds = Credentials.from_service_account_file(
            credentials_path,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.worksheet(sheet_name)
        return worksheet
    except Exception as e:
        logger.error(f"Error initializing Google Sheets client: {e}", exc_info=True)
        raise


def create_sheets_tools() -> List:
    """Create Google Sheets tools for the LangChain agent.
    
    Production-safe: Returns empty list if not configured, never crashes the app.
    
    Returns:
        List of LangChain tools for Google Sheets operations.
        Returns empty list if Google Sheets is not configured or fails to initialize.
    """
    tools = []
    
    # Check if Google Sheets is configured
    if not SHEETS_AVAILABLE:
        logger.info("Google Sheets libraries not available. Skipping sheets tools creation.")
        logger.info("To enable: pip install gspread google-auth")
        return []
    
    credentials_path = os.getenv("GOOGLE_SHEETS_CREDENTIALS_PATH")
    spreadsheet_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    
    if not credentials_path or not spreadsheet_id:
        logger.info("Google Sheets not configured (missing GOOGLE_SHEETS_CREDENTIALS_PATH or GOOGLE_SHEETS_SPREADSHEET_ID). Skipping sheets tools.")
        logger.info("To enable: Set GOOGLE_SHEETS_CREDENTIALS_PATH and GOOGLE_SHEETS_SPREADSHEET_ID environment variables")
        return []
    
    # Validate credentials file exists (production check)
    if not os.path.exists(credentials_path):
        logger.warning(f"Google Sheets credentials file not found: {credentials_path}")
        logger.warning("Skipping sheets tools. Ensure credentials file is mounted in Docker.")
        return []
    
    # Test connection during initialization (production validation)
    try:
        _get_sheets_client()
        logger.info("✓ Google Sheets connection validated successfully")
    except Exception as e:
        logger.warning(f"Google Sheets connection test failed: {e}")
        logger.warning("Skipping sheets tools. Check credentials and permissions.")
        return []
    
    @tool("append_lead_data", args_schema=AppendLeadDataInput)
    def append_lead_data(
        name: Optional[str] = "None",
        selected_course: Optional[str] = "None",
        education_level: Optional[str] = "None",
        goal: Optional[str] = "None",
        phone: Optional[str] = "None",
        notes: Optional[str] = ""
    ) -> str:
        """Append lead data to Google Sheets Leads sheet.
        
        Use this tool right before sharing a demo video link to save lead information.
        All fields are optional - include whatever data you have collected.
        
        Args:
            name: Lead name (or "None" if not collected)
            selected_course: Selected course name (or "None" if not collected)
            education_level: Education level (or "None" if not collected)
            goal: Goal or motivation (or "None" if not collected)
            phone: Phone number (or "None" if not collected)
            notes: Additional notes (optional)
        
        Returns:
            Success message or error message
        """
        try:
            worksheet = _get_sheets_client()
            
            # Prepare row data
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            row_data = [
                name or "None",
                selected_course or "None",
                education_level or "None",
                goal or "None",
                phone or "None",
                current_time,
                "Yes",  # Demo_Link_Sent
                "Demo Shared",  # Conversation_Status
                notes or ""
            ]
            
            # Append row to sheet
            worksheet.append_row(row_data)
            
            logger.info(f"Successfully appended lead data to Google Sheets: {name}, {selected_course}")
            return f"Successfully saved lead data to Google Sheets. Lead: {name}, Course: {selected_course}"
        
        except ImportError as e:
            logger.error(f"Google Sheets libraries not installed: {e}")
            return "Error: Google Sheets functionality not available. Please install required libraries."
        except ValueError as e:
            logger.error(f"Configuration error: {e}")
            return f"Error: {str(e)}"
        except FileNotFoundError as e:
            logger.error(f"Credentials file not found: {e}")
            return f"Error: Credentials file not found. Please check GOOGLE_SHEETS_CREDENTIALS_PATH."
        except Exception as e:
            logger.error(f"Error appending lead data to Google Sheets: {e}", exc_info=True)
            # Return user-friendly error message (don't expose internal details)
            return f"Error saving lead data to Google Sheets. Please try again or contact support if the issue persists."
    
    tools.append(append_lead_data)
    logger.info("✓ Created Google Sheets tool: append_lead_data")
    return tools

