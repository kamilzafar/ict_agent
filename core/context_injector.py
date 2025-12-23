"""Context injector for proactive stage-based context injection using Supabase."""
import logging
from typing import Dict, List, Optional, Any
from core.supabase_service import SupabaseService

logger = logging.getLogger(__name__)


class ContextInjector:
    """Injects relevant Supabase data based on conversation stage.
    
    Optimized for sub-10ms context injection.
    """
    
    # Map conversation stages to relevant data
    STAGE_CONTEXT_MAP = {
        "NEW": [],  # No pre-injection
        "NAME_COLLECTED": [],  # No pre-injection
        "COURSE_SELECTED": [
            "course_details",  # Inject course info, fees, dates
            "course_links"     # Inject demo links, PDFs
        ],
        "EDUCATION_COLLECTED": [
            "course_details"  # Course prerequisites, requirements
        ],
        "GOAL_COLLECTED": [
            "course_details",  # Course alignment with goals
            "faqs"            # Common questions
        ],
        "DEMO_SHARED": [
            "course_links",    # Course page links
            "company_info"     # Contact info, policies
        ],
        "ENROLLED": [
            "company_info"     # Policies, contact info
        ],
        "LOST": []  # No pre-injection
    }
    
    def __init__(self, supabase_service: SupabaseService):
        """Initialize context injector.
        
        Args:
            supabase_service: SupabaseService instance
        """
        self.supabase_service = supabase_service
    
    def get_stage_context(self, stage: str, selected_course: Optional[str] = None) -> str:
        """Get relevant context for a conversation stage (optimized for <10ms).
        
        Args:
            stage: Current conversation stage
            selected_course: Optional selected course name for filtering
        
        Returns:
            Formatted context string to inject into system prompt
        """
        data_to_inject = self.STAGE_CONTEXT_MAP.get(stage, [])
        
        if not data_to_inject:
            return ""
        
        context_parts = []
        
        for data_type in data_to_inject:
            try:
                if data_type == "course_details":
                    courses = self.supabase_service.get_course_details(selected_course)
                    if courses:
                        course = courses[0]
                        formatted = self._format_course_details(course)
                        if formatted:
                            context_parts.append(f"### Course Details:\n{formatted}")
                
                elif data_type == "course_links":
                    courses = self.supabase_service.get_course_links(selected_course)
                    if courses:
                        course = courses[0]
                        formatted = self._format_course_links(course)
                        if formatted:
                            context_parts.append(f"### Course Links:\n{formatted}")
                
                elif data_type == "faqs":
                    faqs = self.supabase_service.get_faqs(limit=5)
                    if faqs:
                        formatted = self._format_faqs(faqs)
                        if formatted:
                            context_parts.append(f"### FAQs:\n{formatted}")
                
                elif data_type == "company_info":
                    company_info = self.supabase_service.get_company_info()
                    if company_info:
                        formatted = self._format_company_info(company_info)
                        if formatted:
                            context_parts.append(f"### Company Information:\n{formatted}")
            
            except Exception as e:
                logger.error(f"Error getting context for {data_type}: {e}")
                continue
        
        if context_parts:
            return "\n\n" + "\n\n".join(context_parts) + "\n\n"
        
        return ""
    
    def _format_course_details(self, course: Dict[str, Any]) -> str:
        """Format course details for context (optimized)."""
        parts = []
        for key, value in course.items():
            if value is not None and value != "" and key != "id":
                parts.append(f"{key}: {value}")
        return "\n".join(parts) if parts else ""
    
    def _format_course_links(self, course: Dict[str, Any]) -> str:
        """Format course links for context (optimized)."""
        parts = []
        if course.get("course_name"):
            parts.append(f"Course: {course['course_name']}")
        if course.get("demo_link"):
            parts.append(f"Demo_Link: {course['demo_link']}")
        if course.get("pdf_link"):
            parts.append(f"Pdf_Link: {course['pdf_link']}")
        if course.get("course_link"):
            parts.append(f"Course_Link: {course['course_link']}")
        return " | ".join(parts) if parts else ""
    
    def _format_faqs(self, faqs: List[Dict[str, Any]]) -> str:
        """Format FAQs for context (optimized)."""
        formatted = []
        for i, faq in enumerate(faqs, 1):
            parts = []
            if faq.get("course_name"):
                parts.append(f"Course: {faq['course_name']}")
            if faq.get("question"):
                parts.append(f"Question: {faq['question']}")
            if faq.get("answer"):
                parts.append(f"Answer: {faq['answer']}")
            if parts:
                formatted.append(f"FAQ {i}:\n" + " | ".join(parts))
        return "\n\n".join(formatted) if formatted else ""
    
    def _format_company_info(self, company_info: Dict[str, Any]) -> str:
        """Format company info for context (optimized).
        
        Company info is stored as key-value pairs (field_name, field_value).
        """
        parts = []
        for field_name, field_value in company_info.items():
            if field_value is not None and field_value != "":
                parts.append(f"{field_name}: {field_value}")
        return "\n".join(parts) if parts else ""

