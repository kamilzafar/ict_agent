"""Context injector for proactive stage-based context injection."""
import logging
from typing import Dict, List, Optional, Any
from core.sheets_cache import GoogleSheetsCacheService

logger = logging.getLogger(__name__)


class ContextInjector:
    """Injects relevant Google Sheets data based on conversation stage."""
    
    # Map conversation stages to relevant sheet data
    STAGE_CONTEXT_MAP = {
        "NEW": [],  # No pre-injection
        "NAME_COLLECTED": [],  # No pre-injection
        "COURSE_SELECTED": [
            "Course_Details",  # Inject course info, fees, dates
            "Course_Links"     # Inject demo links, PDFs
        ],
        "EDUCATION_COLLECTED": [
            "Course_Details"  # Course prerequisites, requirements
        ],
        "GOAL_COLLECTED": [
            "Course_Details",  # Course alignment with goals
            "FAQs"            # Common questions
        ],
        "DEMO_SHARED": [
            "Course_Links",    # Course page links
            "Company_Info"     # Contact info, policies
        ],
        "ENROLLED": [
            "Company_Info"     # Policies, contact info
        ],
        "LOST": []  # No pre-injection
    }
    
    def __init__(self, cache_service: GoogleSheetsCacheService):
        """Initialize context injector.
        
        Args:
            cache_service: Google Sheets cache service instance
        """
        self.cache_service = cache_service
    
    def get_stage_context(self, stage: str, selected_course: Optional[str] = None) -> str:
        """Get relevant context for a conversation stage.
        
        Args:
            stage: Current conversation stage
            selected_course: Optional selected course name for filtering
        
        Returns:
            Formatted context string to inject into system prompt
        """
        sheets_to_inject = self.STAGE_CONTEXT_MAP.get(stage, [])
        
        if not sheets_to_inject:
            return ""
        
        context_parts = []
        
        for sheet_name in sheets_to_inject:
            try:
                # Get sheet data from cache
                sheet_data = self.cache_service.get_sheet_data(sheet_name)
                
                if not sheet_data:
                    logger.warning(f"No cached data for {sheet_name}")
                    continue
                
                # Format sheet data for context
                formatted_data = self._format_sheet_data(sheet_name, sheet_data, selected_course)
                
                if formatted_data:
                    context_parts.append(f"### {sheet_name} Data:\n{formatted_data}")
            
            except Exception as e:
                logger.error(f"Error getting context from {sheet_name}: {e}")
                continue
        
        if context_parts:
            return "\n\n" + "\n\n".join(context_parts) + "\n\n"
        
        return ""
    
    def _format_sheet_data(self, sheet_name: str, data: List[List[str]], filter_course: Optional[str] = None) -> str:
        """Format sheet data for context injection.
        
        Args:
            sheet_name: Name of the sheet
            data: Sheet data (list of rows)
            filter_course: Optional course name to filter by
        
        Returns:
            Formatted string representation of relevant data
        """
        if not data:
            return ""
        
        headers = data[0] if data else []
        rows = data[1:] if len(data) > 1 else []
        
        # Filter rows if course filter is specified
        if filter_course and headers:
            # Try to find course column
            course_col_idx = None
            for idx, header in enumerate(headers):
                if 'course' in header.lower() or 'name' in header.lower():
                    course_col_idx = idx
                    break
            
            if course_col_idx is not None:
                filtered_rows = []
                filter_lower = filter_course.lower()
                for row in rows:
                    if course_col_idx < len(row) and filter_lower in row[course_col_idx].lower():
                        filtered_rows.append(row)
                rows = filtered_rows
        
        # Limit rows to prevent token overflow
        max_rows = 20
        rows = rows[:max_rows]
        
        # Format as readable text
        formatted_lines = []
        
        for row in rows:
            row_parts = []
            for col_idx, value in enumerate(row):
                if col_idx < len(headers) and value:
                    header = headers[col_idx]
                    row_parts.append(f"{header}: {value}")
            
            if row_parts:
                formatted_lines.append(" | ".join(row_parts))
        
        if formatted_lines:
            return "\n".join(formatted_lines)
        
        return ""
    
    def search_and_inject(self, query: str, top_k: int = 3) -> str:
        """Search cached data and return formatted results for injection.
        
        Args:
            query: Search query
            top_k: Number of results to return
        
        Returns:
            Formatted search results
        """
        try:
            results = self.cache_service.search_cached_data(query, top_k=top_k)
            
            if not results:
                return ""
            
            formatted_results = []
            for i, doc in enumerate(results, 1):
                content = doc.page_content
                metadata = doc.metadata
                sheet_name = metadata.get("sheet_name", "Unknown")
                
                formatted_results.append(f"[Result {i} from {sheet_name}]: {content}")
            
            return "\n\n".join(formatted_results)
        
        except Exception as e:
            logger.error(f"Error in search_and_inject: {e}")
            return ""

