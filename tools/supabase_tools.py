"""Optimized Supabase database tools for LangChain agents.

All tools are optimized for sub-10ms query performance.
"""
import logging
from typing import List, Optional
from langchain_core.tools import tool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class CourseLinksInput(BaseModel):
    """Input schema for fetching course links."""
    course_name: str = Field(description="Name of the course to fetch links for (e.g., 'Certified Tax Advisor', 'CTA', 'USA Taxation')")
    link_type: Optional[str] = Field(default=None, description="Type of link to fetch: 'demo' for demo_link, 'pdf' for pdf_link, or None for all links")


class CourseDetailsInput(BaseModel):
    """Input schema for fetching course details."""
    course_name: str = Field(description="Name of the course to fetch details for (e.g., 'Certified Tax Advisor', 'CTA', 'USA Taxation')")
    field: Optional[str] = Field(default=None, description="Specific field to fetch (e.g., 'course_fee', 'duration', 'professor_name') or None for all details")


class FAQsInput(BaseModel):
    """Input schema for fetching FAQs."""
    query: Optional[str] = Field(default=None, description="Search query to find relevant FAQs, or None for all FAQs")
    course_name: Optional[str] = Field(default=None, description="Optional course name to filter FAQs by")
    top_k: int = Field(default=5, description="Number of FAQs to return")


class ProfessorInput(BaseModel):
    """Input schema for fetching professor information."""
    professor_name: Optional[str] = Field(default=None, description="Name of the professor to fetch info for, or None for all professors")
    course_name: Optional[str] = Field(default=None, description="Course name to find associated professor")


class CompanyInfoInput(BaseModel):
    """Input schema for fetching company information."""
    field: Optional[str] = Field(default=None, description="Specific field to fetch (e.g., 'contact_number', 'website') or None for all info")


def create_supabase_tools(supabase_service) -> List:
    """Create all optimized Supabase database tools for the LangChain agent.
    
    All tools are optimized for sub-10ms query performance.
    
    Args:
        supabase_service: SupabaseService instance
    
    Returns:
        List of LangChain tools for fetching data from Supabase. Returns empty list if
        supabase_service is not provided.
    """
    if not supabase_service:
        logger.warning("No supabase_service provided, skipping Supabase tools creation")
        return []
    
    tools = []
    
    # 1. Course Links Tool (optimized)
    @tool("fetch_course_links", args_schema=CourseLinksInput)
    def fetch_course_links(course_name: str, link_type: Optional[str] = None) -> str:
        """Fetch course links from database. Use for demo links, PDF links, or course page links.
        
        Use this tool when you need to share any link with the user. Returns actual URLs.
        Do NOT use append_lead_to_rag_sheets for links - that tool only saves data.
        
        Args:
            course_name: Course name (e.g., "CTA", "USA Taxation")
            link_type: "demo" for demo_link, "pdf" for pdf_link, or None for all links
        
        Returns:
            Link URLs or error message
        """
        try:
            courses = supabase_service.get_course_links(course_name)
            
            if not courses:
                return f"Error: No course found matching '{course_name}' in database."
            
            # Use first matching course (optimized: limit(1) in query)
            course = courses[0]
            result_parts = []
            
            if link_type is None or link_type.lower() == "demo":
                if course.get("demo_link"):
                    result_parts.append(f"Demo_Link: {course['demo_link']}")
            
            if link_type is None or link_type.lower() == "pdf":
                if course.get("pdf_link"):
                    result_parts.append(f"Pdf_Link: {course['pdf_link']}")
            
            if link_type is None:
                if course.get("course_link"):
                    result_parts.append(f"Course_Link: {course['course_link']}")
            
            if not result_parts:
                return f"Error: No {link_type or 'links'} found for course '{course_name}'."
            
            return "\n".join(result_parts)
        
        except Exception as e:
            logger.error(f"Error fetching course links: {e}", exc_info=True)
            return f"Error fetching course links: {str(e)}"
    
    tools.append(fetch_course_links)
    
    # 2. Course Details Tool (optimized)
    @tool("fetch_course_details", args_schema=CourseDetailsInput)
    def fetch_course_details(course_name: str, field: Optional[str] = None) -> str:
        """Fetch course information from database.
        
        Returns fees, duration, dates, professor, locations, enrollment status, benefits, description.
        
        Args:
            course_name: Course name (e.g., "CTA", "USA Taxation")
            field: Optional specific field (e.g., "course_fee", "duration")
        
        Returns:
            Course details or error message
        """
        try:
            courses = supabase_service.get_course_details(course_name)
            
            if not courses:
                return f"Error: No course found matching '{course_name}' in database."
            
            course = courses[0]  # Optimized: limit(1) in query
            
            if field:
                # Return specific field (fast lookup)
                field_lower = field.lower().replace(" ", "_")
                value = course.get(field_lower) or course.get(field)
                if value:
                    return f"{field}: {value}"
                return f"Error: Field '{field}' not found. Available fields: {', '.join(course.keys())}"
            else:
                # Return all fields
                result_parts = []
                for key, value in course.items():
                    if value is not None and value != "" and key != "id":
                        result_parts.append(f"{key}: {value}")
                
                if result_parts:
                    return "\n".join(result_parts)
                return f"Error: No data found for course '{course_name}'"
        
        except Exception as e:
            logger.error(f"Error fetching course details: {e}", exc_info=True)
            return f"Error fetching course details: {str(e)}"
    
    # 3. FAQs Tool (optimized)
    @tool("fetch_faqs", args_schema=FAQsInput)
    def fetch_faqs(query: Optional[str] = None, course_name: Optional[str] = None, top_k: int = 5) -> str:
        """Fetch FAQs from database. Uses optimized search if query provided, otherwise returns top FAQs.
        
        Args:
            query: Optional search query
            course_name: Optional course name to filter by
            top_k: Number of results (default: 5)
        
        Returns:
            FAQs or error message
        """
        try:
            faqs = supabase_service.get_faqs(query, course_name=course_name, limit=top_k)
            
            if not faqs:
                return f"No FAQs found" + (f" matching query: '{query}'" if query else "") + (f" for course: '{course_name}'" if course_name else "")
            
            formatted_faqs = []
            for i, faq in enumerate(faqs, 1):
                parts = []
                if faq.get("course_name"):
                    parts.append(f"Course: {faq['course_name']}")
                if faq.get("question"):
                    parts.append(f"Question: {faq['question']}")
                if faq.get("answer"):
                    parts.append(f"Answer: {faq['answer']}")
                if parts:
                    formatted_faqs.append(f"FAQ {i}:\n" + " | ".join(parts))
            
            if formatted_faqs:
                return "\n\n".join(formatted_faqs)
            return "No FAQs found."
        
        except Exception as e:
            logger.error(f"Error fetching FAQs: {e}", exc_info=True)
            return f"Error fetching FAQs: {str(e)}"
    
    tools.append(fetch_faqs)
    
    # 4. Professor Tool (optimized)
    @tool("fetch_professor_info", args_schema=ProfessorInput)
    def fetch_professor_info(professor_name: Optional[str] = None, course_name: Optional[str] = None) -> str:
        """Fetch professor/trainer information from database.
        
        Returns name, qualifications, experience, specializations, courses, certifications, bio.
        
        Args:
            professor_name: Optional professor name
            course_name: Optional course name to find professor
        
        Returns:
            Professor information or error message
        """
        try:
            professors = supabase_service.get_professor_info(professor_name, course_name)
            
            if not professors:
                return "Error: No professor found matching criteria."
            
            formatted_results = []
            for prof in professors[:5]:  # Limit to 5 for speed
                parts = []
                # Format key fields nicely
                if prof.get("full_name"):
                    parts.append(f"Name: {prof['full_name']}")
                if prof.get("display_name_for_students"):
                    parts.append(f"Display Name: {prof['display_name_for_students']}")
                if prof.get("qualifications"):
                    parts.append(f"Qualifications: {prof['qualifications']}")
                if prof.get("total_years_of_experience"):
                    parts.append(f"Experience: {prof['total_years_of_experience']} years")
                if prof.get("specializations"):
                    parts.append(f"Specializations: {prof['specializations']}")
                if prof.get("courses_currently_teaching"):
                    parts.append(f"Teaching: {prof['courses_currently_teaching']}")
                if prof.get("certifications"):
                    parts.append(f"Certifications: {prof['certifications']}")
                if prof.get("short_bio_for_agent"):
                    parts.append(f"Bio: {prof['short_bio_for_agent']}")
                if parts:
                    formatted_results.append(" | ".join(parts))
            
            if formatted_results:
                return "\n\n".join(formatted_results)
            return "No professor information found."
        
        except Exception as e:
            logger.error(f"Error fetching professor info: {e}", exc_info=True)
            return f"Error fetching professor info: {str(e)}"
    
    tools.append(fetch_professor_info)
    
    # 5. Company Info Tool (optimized)
    @tool("fetch_company_info", args_schema=CompanyInfoInput)
    def fetch_company_info(field: Optional[str] = None) -> str:
        """Fetch company information from database.
        
        Company info is stored as key-value pairs. Returns contact numbers, emails, social media, website, locations, hours, statistics.
        
        Args:
            field: Optional specific field name (e.g., "Main Contact Number", "Website URL")
        
        Returns:
            Company information or error message
        """
        try:
            company_info = supabase_service.get_company_info(field_name=field)
            
            if not company_info:
                return "Error: Company information not available in database."
            
            if field:
                # Return specific field (fast lookup)
                value = company_info.get(field)
                if value:
                    return f"{field}: {value}"
                return f"Error: Field '{field}' not found. Available fields: {', '.join(company_info.keys()) if isinstance(company_info, dict) else 'N/A'}"
            else:
                # Return all fields
                result_parts = []
                for key, value in company_info.items():
                    if value is not None and value != "":
                        result_parts.append(f"{key}: {value}")
                
                if result_parts:
                    return "\n".join(result_parts)
                return "No company information found."
        
        except Exception as e:
            logger.error(f"Error fetching company info: {e}", exc_info=True)
            return f"Error fetching company info: {str(e)}"
    
    tools.append(fetch_company_info)
    
    logger.info(f"Created {len(tools)} optimized Supabase tools")
    return tools

