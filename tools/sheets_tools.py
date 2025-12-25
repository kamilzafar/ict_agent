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
    """Input schema for appending/updating lead data to Google Sheets.
    
    All fields are optional. The tool will:
    - Update existing row if name or phone matches
    - Append new row if no match found
    - Merge partial data with existing row data
    """
    name: Optional[str] = Field(default=None, description="Lead name (optional)")
    selected_course: Optional[str] = Field(default=None, description="Selected course name (optional)")
    education_level: Optional[str] = Field(default=None, description="Education level (optional)")
    goal: Optional[str] = Field(default=None, description="Goal or motivation (optional)")
    phone: Optional[str] = Field(default=None, description="Phone number (optional)")
    notes: Optional[str] = Field(default=None, description="Additional notes (optional)")
    add_timestamp: Optional[bool] = Field(default=False, description="If True, add current timestamp to the row")


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


def _find_existing_row(worksheet, name: Optional[str] = None, phone: Optional[str] = None) -> Optional[int]:
    """Find existing row by name or phone number.
    
    Args:
        worksheet: Google Sheets worksheet object
        name: Lead name to search for
        phone: Phone number to search for
    
    Returns:
        Row number (1-indexed) if found, None otherwise
    """
    try:
        # Get all values from the sheet
        all_values = worksheet.get_all_values()
        
        if not all_values:
            return None
        
        # Assume first row is header, data starts from row 2
        # Expected columns: Name, Course, Education, Goal, Phone, Timestamp, Demo_Link_Sent, Status, Notes
        # Adjust column indices based on your actual sheet structure
        name_col_idx = 0  # Column A (Name)
        phone_col_idx = 4  # Column E (Phone)
        
        for idx, row in enumerate(all_values[1:], start=2):  # Start from row 2 (skip header)
            row_name = row[name_col_idx].strip() if len(row) > name_col_idx else ""
            row_phone = row[phone_col_idx].strip() if len(row) > phone_col_idx else ""
            
            # Match on name (case-insensitive, ignore whitespace)
            if name and row_name and name.strip().lower() == row_name.lower():
                return idx
            
            # Match on phone (exact match, ignore whitespace and formatting)
            if phone and row_phone:
                # Normalize phone numbers (remove spaces, dashes, etc.)
                normalized_phone = ''.join(filter(str.isdigit, phone.strip()))
                normalized_row_phone = ''.join(filter(str.isdigit, row_phone))
                if normalized_phone and normalized_phone == normalized_row_phone:
                    return idx
        
        return None
    except Exception as e:
        logger.error(f"Error finding existing row: {e}", exc_info=True)
        return None


def _update_row(worksheet, row_num: int, new_data: dict, add_timestamp: bool = False):
    """Update existing row with new data, merging intelligently with existing values.
    
    Smart merge logic:
    - Only updates fields that are empty in existing row (fills gaps)
    - Only updates fields with new non-empty values (doesn't overwrite with empty)
    - Preserves existing data when new data is not provided
    
    Args:
        worksheet: Google Sheets worksheet object
        row_num: Row number to update (1-indexed)
        new_data: Dictionary with field names and new values (only provided fields)
        add_timestamp: If True, add/update current timestamp
    """
    try:
        # Get existing row data
        existing_row = worksheet.row_values(row_num)
        
        # Expected column order: Name, Course, Education, Goal, Phone, Timestamp, Demo_Link_Sent, Status, Notes
        col_mapping = {
            'name': 0,
            'selected_course': 1,
            'education_level': 2,
            'goal': 3,
            'phone': 4,
            'timestamp': 5,
            'demo_link_sent': 6,
            'conversation_status': 7,
            'notes': 8
        }
        
        # Prepare update values (only update when appropriate)
        updates = {}
        for field, value in new_data.items():
            # Skip None or empty values - don't overwrite existing data with empty
            if value is None or value == "":
                continue
                
            col_idx = col_mapping.get(field)
            if col_idx is not None:
                # Extend row if needed
                while len(existing_row) <= col_idx:
                    existing_row.append("")
                
                existing_value = existing_row[col_idx].strip() if col_idx < len(existing_row) else ""
                
                # Smart merge: Only update if:
                # 1. Field is empty in existing row (fill the gap)
                # 2. New value is different from existing (update with new data)
                # Never overwrite existing data with empty values
                if existing_value == "" or existing_value == "None" or existing_value.lower() == "none":
                    # Fill empty field
                    updates[col_idx] = value
                    logger.debug(f"Updating empty field '{field}' with value: {value}")
                elif existing_value.lower() != value.lower():
                    # Update with new value (new data takes precedence)
                    updates[col_idx] = value
                    logger.debug(f"Updating field '{field}' from '{existing_value}' to '{value}'")
                else:
                    # Values are the same, skip update
                    logger.debug(f"Skipping update for '{field}' - value unchanged: {value}")
        
        # Add/update timestamp if requested (always update timestamp when requested)
        if add_timestamp:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            updates[col_mapping['timestamp']] = timestamp
            logger.debug(f"Adding/updating timestamp: {timestamp}")
        
        # Apply updates
        if updates:
            for col_idx, value in updates.items():
                worksheet.update_cell(row_num, col_idx + 1, value)  # gspread uses 1-indexed
            
            updated_field_names = [k for k, v in col_mapping.items() if v in updates]
            logger.info(f"Updated row {row_num} with fields: {updated_field_names}")
        else:
            logger.info(f"No updates needed for row {row_num} - all fields already have values or no new data provided")
        
    except Exception as e:
        logger.error(f"Error updating row {row_num}: {e}", exc_info=True)
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
        name: Optional[str] = None,
        selected_course: Optional[str] = None,
        education_level: Optional[str] = None,
        goal: Optional[str] = None,
        phone: Optional[str] = None,
        notes: Optional[str] = None,
        add_timestamp: Optional[bool] = False
    ) -> str:
        """Append or update lead data in Google Sheets Leads sheet.
        
        This tool can be called with 1 or more fields. It will:
        - Update existing row if name or phone matches (smart merge - only updates provided fields)
        - Append new row if no match found
        - Preserve existing data when updating (doesn't overwrite with empty values)
        
        All fields are optional - you can call with just 1-2 fields and it will append/update accordingly.
        When add_timestamp=True, it will add/update the current timestamp.
        
        Use this tool right before sharing a demo video link to save lead information.
        
        Args:
            name: Lead name (optional)
            selected_course: Selected course name (optional)
            education_level: Education level (optional)
            goal: Goal or motivation (optional)
            phone: Phone number (optional)
            notes: Additional notes (optional)
            add_timestamp: If True, add/update current timestamp with now() time (optional, default False)
        
        Returns:
            Success message indicating whether row was updated or appended, and which fields were saved
        """
        try:
            worksheet = _get_sheets_client()
            
            # Prepare data dictionary (only include non-None, non-empty values)
            # This ensures we don't overwrite existing data with empty values
            data_dict = {}
            if name is not None and name.strip():
                data_dict['name'] = name.strip()
            if selected_course is not None and selected_course.strip():
                data_dict['selected_course'] = selected_course.strip()
            if education_level is not None and education_level.strip():
                data_dict['education_level'] = education_level.strip()
            if goal is not None and goal.strip():
                data_dict['goal'] = goal.strip()
            if phone is not None and phone.strip():
                data_dict['phone'] = phone.strip()
            if notes is not None and notes.strip():
                data_dict['notes'] = notes.strip()
            
            # Check if we have any data to save (including timestamp)
            if not data_dict and not add_timestamp:
                return "No data provided to save. Please provide at least one field or set add_timestamp=True."
            
            # Try to find existing row by name or phone (for matching)
            existing_row_num = None
            search_name = data_dict.get('name')
            search_phone = data_dict.get('phone')
            
            if search_name:
                existing_row_num = _find_existing_row(worksheet, name=search_name)
            if not existing_row_num and search_phone:
                existing_row_num = _find_existing_row(worksheet, phone=search_phone)
            
            if existing_row_num:
                # Update existing row with smart merge
                _update_row(worksheet, existing_row_num, data_dict, add_timestamp=add_timestamp)
                
                # Get list of fields that were actually updated
                updated_fields = []
                if data_dict:
                    # Check which fields were provided
                    for field in data_dict.keys():
                        updated_fields.append(field.replace('_', ' '))
                if add_timestamp:
                    updated_fields.append("timestamp")
                
                lead_identifier = search_name or search_phone or "lead"
                logger.info(f"Updated existing row {existing_row_num} for {lead_identifier}")
                
                if updated_fields:
                    return f"Successfully updated lead data in Google Sheets (row {existing_row_num}). Updated fields: {', '.join(updated_fields)}"
                else:
                    return f"Lead data already exists in Google Sheets (row {existing_row_num}). No updates needed."
            else:
                # Append new row (only include provided fields, empty strings for others)
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if add_timestamp else ""
                
                # Prepare row data - only include provided values, empty strings for missing fields
                row_data = [
                    data_dict.get('name', ''),
                    data_dict.get('selected_course', ''),
                    data_dict.get('education_level', ''),
                    data_dict.get('goal', ''),
                    data_dict.get('phone', ''),
                    current_time,  # Timestamp (empty string if not requested)
                    "Yes" if data_dict.get('selected_course') else "",  # Demo_Link_Sent
                    "Demo Shared" if data_dict.get('selected_course') else "",  # Conversation_Status
                    data_dict.get('notes', '')
                ]
                
                # Append row to sheet
                worksheet.append_row(row_data)
                
                # Get list of saved fields
                saved_fields = list(data_dict.keys())
                if add_timestamp:
                    saved_fields.append("timestamp")
                
                lead_name = data_dict.get('name', 'Unknown')
                course = data_dict.get('selected_course', 'No course')
                logger.info(f"Appended new lead data to Google Sheets: {lead_name}, {course}")
                
                field_names = [f.replace('_', ' ') for f in saved_fields]
                return f"Successfully saved lead data to Google Sheets (new row). Saved fields: {', '.join(field_names)}"
        
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
            logger.error(f"Error saving lead data to Google Sheets: {e}", exc_info=True)
            # Return user-friendly error message (don't expose internal details)
            return f"Error saving lead data to Google Sheets. Please try again or contact support if the issue persists."
    
    tools.append(append_lead_data)
    logger.info("✓ Created Google Sheets tool: append_lead_data")
    return tools

