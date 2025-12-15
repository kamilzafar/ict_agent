"""Google Sheets data fetching tools for LangChain agents.

This module provides a comprehensive set of LangChain tools that enable agents to
fetch data from Google Sheets. All tools interact with the cached Google Sheets
data through the GoogleSheetsCacheService.

Available Tools:
    - fetch_course_links: Fetch demo links, PDF links, and course page links
    - fetch_course_details: Fetch course information (fees, duration, dates, etc.)
    - fetch_faqs: Fetch frequently asked questions with semantic search
    - fetch_professor_info: Fetch professor/trainer information
    - fetch_company_info: Fetch company information and contact details

Main Functions:
    - create_google_sheets_tools(): Create all Google Sheets tools
    - create_course_links_fetcher_tool(): Create only Course_Links tool (legacy)
"""
import logging
from typing import List, Optional, Dict, Any
from langchain_core.tools import tool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class CourseLinksInput(BaseModel):
    """Input schema for fetching Course_Links."""
    course_name: str = Field(description="Name of the course to fetch links for (e.g., 'Certified Tax Advisor', 'CTA', 'USA Taxation')")
    link_type: Optional[str] = Field(default=None, description="Type of link to fetch: 'demo' for Demo_Link, 'pdf' for Pdf_Link, or None for all links")


class CourseDetailsInput(BaseModel):
    """Input schema for fetching Course_Details."""
    course_name: str = Field(description="Name of the course to fetch details for (e.g., 'Certified Tax Advisor', 'CTA', 'USA Taxation')")
    field: Optional[str] = Field(default=None, description="Specific field to fetch (e.g., 'Course_Fee', 'Course_Duration', 'Professor_Name') or None for all details")


class FAQsInput(BaseModel):
    """Input schema for fetching FAQs."""
    query: Optional[str] = Field(default=None, description="Search query to find relevant FAQs, or None for all FAQs")
    top_k: int = Field(default=5, description="Number of FAQs to return")


class ProfessorInput(BaseModel):
    """Input schema for fetching professor information."""
    professor_name: Optional[str] = Field(default=None, description="Name of the professor to fetch info for, or None for all professors")
    course_name: Optional[str] = Field(default=None, description="Course name to find associated professor")


class CompanyInfoInput(BaseModel):
    """Input schema for fetching company information."""
    field: Optional[str] = Field(default=None, description="Specific field to fetch (e.g., 'Main Contact Number', 'Website URL') or None for all info")


def create_google_sheets_tools(sheets_cache_service) -> List:
    """Create all Google Sheets data fetching tools for the LangChain agent.
    
    This function creates a comprehensive set of tools that allow the agent to fetch
    data from all configured Google Sheets (Course_Details, Course_Links, FAQs, 
    About_Profr, Company_Info).
    
    Args:
        sheets_cache_service: Google Sheets cache service instance
    
    Returns:
        List of LangChain tools for fetching sheet data. Returns empty list if
        sheets_cache_service is not provided.
    """
    if not sheets_cache_service:
        logger.warning("No sheets_cache_service provided, skipping sheet tools creation")
        return []
    
    tools = []
    
    # 1. Course_Links Tool
    @tool("fetch_course_links", args_schema=CourseLinksInput)
    def fetch_course_links(course_name: str, link_type: Optional[str] = None) -> str:
        """Fetch links from Course_Links sheet. Use for demo links, PDF links, or course page links.
        
        Use this tool when you need to share any link with the user. Returns actual URLs.
        Do NOT use append_lead_to_rag_sheets for links - that tool only saves data.
        
        Args:
            course_name: Course name (e.g., "CTA", "USA Taxation")
            link_type: "demo" for Demo_Link, "pdf" for Pdf_Link, or None for all links
        
        Returns:
            Link URLs or error message
        """
        try:
            course_links_data = sheets_cache_service.get_sheet_data("Course_Links")
            
            if not course_links_data:
                return "Error: Course_Links sheet data not available. Please check if the sheet is cached."
            
            if len(course_links_data) < 2:
                return "Error: Course_Links sheet is empty or has no data rows."
            
            headers = course_links_data[0]
            rows = course_links_data[1:]
            
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
                return f"Error: Could not find Course_Name column in Course_Links sheet. Available columns: {', '.join(headers)}"
            
            # Search for matching course
            course_name_lower = course_name.lower()
            matching_rows = []
            
            for row in rows:
                if course_col_idx < len(row):
                    row_course = row[course_col_idx].lower() if row[course_col_idx] else ""
                    if course_name_lower in row_course or row_course in course_name_lower:
                        matching_rows.append(row)
            
            if not matching_rows:
                available_courses = [row[course_col_idx] for row in rows if course_col_idx < len(row) and row[course_col_idx]]
                return f"Error: No course found matching '{course_name}' in Course_Links sheet. Available courses: {', '.join(available_courses[:10])}"
            
            # Extract links from first matching row
            result_parts = []
            row = matching_rows[0]
            
            if link_type is None or link_type.lower() == "demo":
                if demo_link_col_idx is not None and demo_link_col_idx < len(row) and row[demo_link_col_idx]:
                    result_parts.append(f"Demo_Link: {row[demo_link_col_idx]}")
            
            if link_type is None or link_type.lower() == "pdf":
                if pdf_link_col_idx is not None and pdf_link_col_idx < len(row) and row[pdf_link_col_idx]:
                    result_parts.append(f"Pdf_Link: {row[pdf_link_col_idx]}")
            
            if link_type is None:
                if course_link_col_idx is not None and course_link_col_idx < len(row) and row[course_link_col_idx]:
                    result_parts.append(f"Course_Link: {row[course_link_col_idx]}")
            
            if not result_parts:
                return f"Error: No {link_type or 'links'} found for course '{course_name}' in Course_Links sheet."
            
            return "\n".join(result_parts)
        
        except Exception as e:
            logger.error(f"Error fetching course links: {e}", exc_info=True)
            return f"Error fetching course links: {str(e)}"
    
    tools.append(fetch_course_links)
    
    # 2. Course_Details Tool
    @tool("fetch_course_details", args_schema=CourseDetailsInput)
    def fetch_course_details(course_name: str, field: Optional[str] = None) -> str:
        """Fetch course information from Course_Details sheet.
        
        Returns fees, duration, dates, professor, locations, enrollment status, benefits, description.
        
        Args:
            course_name: Course name (e.g., "CTA", "USA Taxation")
            field: Optional specific field (e.g., "Course_Fee_physical", "Course_Duration")
        
        Returns:
            Course details or error message
        """
        try:
            course_details_data = sheets_cache_service.get_sheet_data("Course_Details")
            
            if not course_details_data:
                return "Error: Course_Details sheet data not available. Please check if the sheet is cached."
            
            if len(course_details_data) < 2:
                return "Error: Course_Details sheet is empty or has no data rows."
            
            headers = course_details_data[0]
            rows = course_details_data[1:]
            
            # Find course name column
            course_col_idx = None
            for idx, header in enumerate(headers):
                header_lower = header.lower()
                if 'course' in header_lower and 'name' in header_lower:
                    course_col_idx = idx
                    break
            
            if course_col_idx is None:
                return f"Error: Could not find Course_Name column. Available columns: {', '.join(headers)}"
            
            # Search for matching course
            course_name_lower = course_name.lower()
            matching_rows = []
            
            for row in rows:
                if course_col_idx < len(row):
                    row_course = row[course_col_idx].lower() if row[course_col_idx] else ""
                    if course_name_lower in row_course or row_course in course_name_lower:
                        matching_rows.append(row)
            
            if not matching_rows:
                available_courses = [row[course_col_idx] for row in rows if course_col_idx < len(row) and row[course_col_idx]]
                return f"Error: No course found matching '{course_name}' in Course_Details sheet. Available courses: {', '.join(available_courses[:10])}"
            
            # Extract details from first matching row
            row = matching_rows[0]
            result_parts = []
            
            if field:
                # Find specific field
                field_lower = field.lower()
                for idx, header in enumerate(headers):
                    if field_lower in header.lower():
                        if idx < len(row) and row[idx]:
                            return f"{header}: {row[idx]}"
                return f"Error: Field '{field}' not found. Available fields: {', '.join(headers)}"
            else:
                # Return all fields
                for idx, header in enumerate(headers):
                    if idx < len(row) and row[idx]:
                        result_parts.append(f"{header}: {row[idx]}")
            
            if result_parts:
                return "\n".join(result_parts)
            return f"Error: No data found for course '{course_name}'"
        
        except Exception as e:
            logger.error(f"Error fetching course details: {e}", exc_info=True)
            return f"Error fetching course details: {str(e)}"
    
    tools.append(fetch_course_details)
    
    # 3. FAQs Tool
    @tool("fetch_faqs", args_schema=FAQsInput)
    def fetch_faqs(query: Optional[str] = None, top_k: int = 5) -> str:
        """Fetch FAQs from FAQs sheet. Uses semantic search if query provided, otherwise returns top FAQs.
        
        Args:
            query: Optional search query
            top_k: Number of results (default: 5)
        
        Returns:
            FAQs or error message
        """
        try:
            if query:
                # Use semantic search
                results = sheets_cache_service.search_cached_data(query, sheet_name="FAQs", top_k=top_k)
                if results:
                    formatted_results = []
                    for i, doc in enumerate(results, 1):
                        content = doc.page_content
                        metadata = doc.metadata
                        formatted_results.append(f"FAQ {i}:\n{content}")
                    return "\n\n".join(formatted_results)
                return f"No FAQs found matching query: '{query}'"
            else:
                # Return all FAQs from cache
                faqs_data = sheets_cache_service.get_sheet_data("FAQs")
                if not faqs_data:
                    return "Error: FAQs sheet data not available."
                
                if len(faqs_data) < 2:
                    return "Error: FAQs sheet is empty."
                
                headers = faqs_data[0]
                rows = faqs_data[1:top_k+1]  # Limit to top_k
                
                formatted_faqs = []
                for i, row in enumerate(rows, 1):
                    row_parts = []
                    for idx, header in enumerate(headers):
                        if idx < len(row) and row[idx]:
                            row_parts.append(f"{header}: {row[idx]}")
                    if row_parts:
                        formatted_faqs.append(f"FAQ {i}:\n" + " | ".join(row_parts))
                
                if formatted_faqs:
                    return "\n\n".join(formatted_faqs)
                return "No FAQs found."
        
        except Exception as e:
            logger.error(f"Error fetching FAQs: {e}", exc_info=True)
            return f"Error fetching FAQs: {str(e)}"
    
    tools.append(fetch_faqs)
    
    # 4. About_Profr (Professor) Tool
    @tool("fetch_professor_info", args_schema=ProfessorInput)
    def fetch_professor_info(professor_name: Optional[str] = None, course_name: Optional[str] = None) -> str:
        """Fetch professor/trainer information from About_Profr sheet.
        
        Returns name, qualifications, experience, associated courses.
        
        Args:
            professor_name: Optional professor name
            course_name: Optional course name to find professor
        
        Returns:
            Professor information or error message
        """
        try:
            prof_data = sheets_cache_service.get_sheet_data("About_Profr")
            
            if not prof_data:
                return "Error: About_Profr sheet data not available."
            
            if len(prof_data) < 2:
                return "Error: About_Profr sheet is empty."
            
            headers = prof_data[0]
            rows = prof_data[1:]
            
            # Find name column
            name_col_idx = None
            course_col_idx = None
            for idx, header in enumerate(headers):
                header_lower = header.lower()
                if 'name' in header_lower or 'display' in header_lower:
                    name_col_idx = idx
                if 'course' in header_lower:
                    course_col_idx = idx
            
            matching_rows = []
            
            if professor_name:
                # Search by professor name
                prof_name_lower = professor_name.lower()
                for row in rows:
                    if name_col_idx is not None and name_col_idx < len(row):
                        row_name = row[name_col_idx].lower() if row[name_col_idx] else ""
                        if prof_name_lower in row_name or row_name in prof_name_lower:
                            matching_rows.append(row)
            elif course_name:
                # Search by course name
                course_name_lower = course_name.lower()
                for row in rows:
                    if course_col_idx is not None and course_col_idx < len(row):
                        row_course = row[course_col_idx].lower() if row[course_col_idx] else ""
                        if course_name_lower in row_course or row_course in course_name_lower:
                            matching_rows.append(row)
            else:
                # Return all professors
                matching_rows = rows
            
            if not matching_rows:
                return f"Error: No professor found matching criteria."
            
            # Format results
            formatted_results = []
            for row in matching_rows[:10]:  # Limit to 10
                row_parts = []
                for idx, header in enumerate(headers):
                    if idx < len(row) and row[idx]:
                        row_parts.append(f"{header}: {row[idx]}")
                if row_parts:
                    formatted_results.append(" | ".join(row_parts))
            
            if formatted_results:
                return "\n\n".join(formatted_results)
            return "No professor information found."
        
        except Exception as e:
            logger.error(f"Error fetching professor info: {e}", exc_info=True)
            return f"Error fetching professor info: {str(e)}"
    
    tools.append(fetch_professor_info)
    
    # 5. Company_Info Tool
    @tool("fetch_company_info", args_schema=CompanyInfoInput)
    def fetch_company_info(field: Optional[str] = None) -> str:
        """Fetch company information from Company_Info sheet.
        
        Returns contact numbers, emails, social media, website, locations, hours, statistics.
        
        Args:
            field: Optional specific field (e.g., "Main Contact Number", "Website URL")
        
        Returns:
            Company information or error message
        """
        try:
            company_data = sheets_cache_service.get_sheet_data("Company_Info")
            
            if not company_data:
                return "Error: Company_Info sheet data not available."
            
            if len(company_data) < 2:
                return "Error: Company_Info sheet is empty."
            
            headers = company_data[0]
            rows = company_data[1:]
            
            # Company_Info is typically in key-value format (Field Name | Field Value)
            if len(headers) >= 2:
                field_name_col = 0
                field_value_col = 1
                
                if field:
                    # Search for specific field
                    field_lower = field.lower()
                    for row in rows:
                        if field_name_col < len(row) and row[field_name_col]:
                            row_field = row[field_name_col].lower()
                            if field_lower in row_field:
                                if field_value_col < len(row) and row[field_value_col]:
                                    return f"{row[field_name_col]}: {row[field_value_col]}"
                    return f"Error: Field '{field}' not found in Company_Info sheet."
                else:
                    # Return all fields
                    result_parts = []
                    for row in rows:
                        if field_name_col < len(row) and field_value_col < len(row):
                            if row[field_name_col] and row[field_value_col]:
                                result_parts.append(f"{row[field_name_col]}: {row[field_value_col]}")
                    
                    if result_parts:
                        return "\n".join(result_parts)
            else:
                # Fallback: treat as regular table
                result_parts = []
                for row in rows[:20]:  # Limit rows
                    row_parts = []
                    for idx, header in enumerate(headers):
                        if idx < len(row) and row[idx]:
                            row_parts.append(f"{header}: {row[idx]}")
                    if row_parts:
                        result_parts.append(" | ".join(row_parts))
                
                if result_parts:
                    return "\n".join(result_parts)
            
            return "No company information found."
        
        except Exception as e:
            logger.error(f"Error fetching company info: {e}", exc_info=True)
            return f"Error fetching company info: {str(e)}"
    
    tools.append(fetch_company_info)
    
    logger.info(f"Created {len(tools)} Google Sheets tools")
    return tools


def create_course_links_fetcher_tool(sheets_cache_service):
    """Create a single Course_Links fetcher tool (for backward compatibility).
    
    This is a convenience function that returns only the Course_Links fetcher tool.
    For full functionality, use create_google_sheets_tools() instead.
    
    Args:
        sheets_cache_service: Google Sheets cache service instance
    
    Returns:
        LangChain tool for fetching Course_Links data, or None if service unavailable
    """
    tools = create_google_sheets_tools(sheets_cache_service)
    # Return the Course_Links tool (first tool in the list)
    return tools[0] if tools else None


# Backward compatibility alias
create_course_links_tool = create_course_links_fetcher_tool

