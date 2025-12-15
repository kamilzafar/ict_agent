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
        
        # Special formatting for Course_Links sheet to make links more visible
        if sheet_name == "Course_Links":
            return self._format_course_links(headers, rows, filter_course)
        
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
    
    def _format_course_links(self, headers: List[str], rows: List[List[str]], filter_course: Optional[str] = None) -> str:
        """Format Course_Links sheet data with emphasis on links.
        
        Args:
            headers: Column headers
            rows: Data rows
            filter_course: Optional course name to filter by
        
        Returns:
            Formatted Course_Links data with clear link visibility
        """
        # Find column indices
        course_col_idx = None
        demo_link_col_idx = None
        pdf_link_col_idx = None
        course_link_col_idx = None
        
        for idx, header in enumerate(headers):
            header_lower = header.lower()
            if 'course' in header_lower and ('name' in header_lower or 'course' == header_lower):
                course_col_idx = idx
            elif 'demo' in header_lower and 'link' in header_lower:
                demo_link_col_idx = idx
            elif 'pdf' in header_lower and 'link' in header_lower:
                pdf_link_col_idx = idx
            elif 'course_link' in header_lower or 'course_page' in header_lower:
                course_link_col_idx = idx
        
        if course_col_idx is None:
            # Fallback to generic formatting
            return self._format_generic_sheet(headers, rows, filter_course)
        
        # Filter by course if specified
        if filter_course:
            filter_lower = filter_course.lower()
            rows = [
                row for row in rows 
                if course_col_idx < len(row) and row[course_col_idx] 
                and filter_lower in row[course_col_idx].lower()
            ]
        
        # Format with emphasis on links
        formatted_lines = []
        for row in rows:
            if course_col_idx >= len(row) or not row[course_col_idx]:
                continue
            
            course_name = row[course_col_idx]
            parts = [f"Course: {course_name}"]
            
            if demo_link_col_idx is not None and demo_link_col_idx < len(row) and row[demo_link_col_idx]:
                parts.append(f"Demo_Link: {row[demo_link_col_idx]}")
            
            if pdf_link_col_idx is not None and pdf_link_col_idx < len(row) and row[pdf_link_col_idx]:
                parts.append(f"Pdf_Link: {row[pdf_link_col_idx]}")
            
            if course_link_col_idx is not None and course_link_col_idx < len(row) and row[course_link_col_idx]:
                parts.append(f"Course_Link: {row[course_link_col_idx]}")
            
            if len(parts) > 1:  # At least course name + one link
                formatted_lines.append(" | ".join(parts))
        
        if formatted_lines:
            return "\n".join(formatted_lines)
        
        return ""
    
    def _format_generic_sheet(self, headers: List[str], rows: List[List[str]], filter_course: Optional[str] = None) -> str:
        """Generic sheet formatting fallback."""
        formatted_lines = []
        for row in rows:
            row_parts = []
            for col_idx, value in enumerate(row):
                if col_idx < len(headers) and value:
                    header = headers[col_idx]
                    row_parts.append(f"{header}: {value}")
            if row_parts:
                formatted_lines.append(" | ".join(row_parts))
        return "\n".join(formatted_lines)
    
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

