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
    course_name: str = Field(
        description="EXACT course name from database (e.g., 'Certified Tax Advisor - Online', 'USA Taxation Course', 'Saudi Taxation Course'). Use the full course name, not abbreviations."
    )
    link_type: Optional[str] = Field(
        default=None,
        description="Type of link to fetch: 'demo' for demo video link, 'pdf' for PDF/brochure link, or None for all available links"
    )


class CourseDetailsInput(BaseModel):
    """Input schema for fetching course details."""
    course_name: str = Field(
        description="EXACT course name from database. Examples: 'Certified Tax Advisor - Online', 'USA Taxation Course', 'UAE Taxation Course', 'Saudi Taxation Course', 'Advance Taxation & Litigations'. Use full course name as stored in Supabase, not abbreviations."
    )
    field: Optional[str] = Field(
        default=None,
        description="Specific field to fetch: 'course_fee_physical', 'course_fee_online', 'course_duration', 'professor_name', 'course_start_date_or_last_enrollment_date', 'mode_of_courses', 'course_benefits'. Leave as None to get ALL course details (recommended for pricing queries)."
    )


class FAQsInput(BaseModel):
    """Input schema for fetching FAQs."""
    query: Optional[str] = Field(
        default=None,
        description="Natural language search query to find relevant FAQs (e.g., 'installment', 'refund policy', 'certificate', 'job guarantee'). Use keywords from user's question. Leave as None to get general FAQs."
    )
    course_name: Optional[str] = Field(
        default=None,
        description="EXACT course name from database (e.g., 'USA Taxation Course') to filter FAQs specific to that course. Leave as None for general FAQs."
    )
    top_k: int = Field(
        default=5,
        description="Number of FAQ results to return (default: 5). Use 3 for quick answers, 10 for comprehensive searches."
    )


class ProfessorInput(BaseModel):
    """Input schema for fetching professor information."""
    professor_name: Optional[str] = Field(
        default=None,
        description="Professor's name (e.g., 'Rai Basharat Ali', 'Sir Rai Basharat Ali'). Leave as None if you only have course_name."
    )
    course_name: Optional[str] = Field(
        default=None,
        description="EXACT course name from database (e.g., 'Certified Tax Advisor - Online', 'USA Taxation Course') to find the professor teaching that course. Use this when user asks 'USA Taxation ka teacher kaun hai?'. Leave as None if you have professor_name."
    )


class CompanyInfoInput(BaseModel):
    """Input schema for fetching company information."""
    field: Optional[str] = Field(
        default=None,
        description="Specific field to fetch (e.g., 'Main Contact Number', 'WhatsApp Number', 'Email Address', 'Website URL', 'Facebook Page', 'Instagram Handle', 'Office Location'). Leave as None to get ALL company information."
    )


class SearchCoursesInput(BaseModel):
    """Input schema for searching courses."""
    search_term: str = Field(
        description="Keywords to search in course names and descriptions (e.g., 'tax', 'USA', 'accounting', 'UAE', 'export', 'stock exchange'). Searches both course names and descriptions."
    )
    limit: int = Field(
        default=10,
        description="Maximum number of course results to return (default: 10). Use 5 for quick searches, 15 for comprehensive listings."
    )


class AppendLeadDataInput(BaseModel):
    """Input schema for appending/updating lead data in Supabase."""
    name: Optional[str] = Field(
        default=None,
        description="Lead's full name (e.g., 'Hassan Ahmed', 'Ali Khan'). Collect this during conversation."
    )
    phone: Optional[str] = Field(
        default=None,
        description="Lead's phone number (e.g., '03001234567', '+923001234567') OR conversation_id from chat API (e.g., 'wa_1234567890'). Used to identify returning customers. Stores in phone_number column."
    )
    selected_course: Optional[str] = Field(
        default=None,
        description="EXACT course name they selected (e.g., 'Certified Tax Advisor - Online', 'USA Taxation Course'). REQUIRED field - always provide the course they're interested in."
    )
    education_level: Optional[str] = Field(
        default=None,
        description="Their education level (e.g., 'Intermediate', 'Bachelors', 'Masters', 'CA', 'ACCA'). Collect when qualifying the lead."
    )
    goal: Optional[str] = Field(
        default=None,
        description="Their goal/motivation in their own words (e.g., 'Start own practice', 'Get job in Big 4', 'Learn for business'). Collect to understand their needs."
    )
    notes: Optional[str] = Field(
        default=None,
        description="Additional notes about the conversation, their concerns, objections, or specific requests (e.g., 'Asked about installments', 'Wants to join next batch', 'Referred by friend')."
    )
    add_timestamp: bool = Field(
        default=True,
        description="Always True - timestamp is added automatically to track when lead was created/updated."
    )


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
        """Always use this tool to Fetch course links from database. Use for demo links, PDF links, or course page links.
        
        Use this tool when you need to share any link with the user. Returns actual URLs.
        
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
        """ALWAYS use this tool to fetch course information from database.

        USE THIS TOOL FOR:
        - Pricing/Fee/Cost queries ("fee kitni hai", "price kya hai", "pricing share karo")
        - Duration/Length ("kitne mahine ka hai", "duration kya hai")
        - Start dates ("kab start hoga", "enrollment date")
        - Professor/Teacher info ("teacher kaun hai")
        - Locations ("kahan classes hain")
        - Course benefits, description, mode (online/physical)

        Returns ALL available course data including:
        - course_fee_physical, course_fee_online, course_fee_hibernate (if available)
        - course_duration, course_start_date_or_last_enrollment_date
        - professor_name, mode_of_courses
        - location_islamabad, location_karachi, location_lahore
        - course_benefits, course_description
        - enrollment_status, online_available, physical_available

        Args:
            course_name: Course name (e.g., "CTA", "USA Taxation", "Transfer Pricing")
            field: Optional specific field (e.g., "course_fee_physical", "duration")

        Returns:
            Course details with ALL available fields or error message
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
                        # Clean Unicode formatting characters to avoid encoding issues
                        if isinstance(value, str):
                            # Replace bold/italic Unicode characters with regular ASCII
                            import unicodedata
                            # Normalize to closest ASCII equivalent
                            value_clean = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
                            result_parts.append(f"{key}: {value_clean}")
                        else:
                            result_parts.append(f"{key}: {value}")

                if result_parts:
                    return "\n".join(result_parts)
                return f"Error: No data found for course '{course_name}'"
        
        except Exception as e:
            logger.error(f"Error fetching course details: {e}", exc_info=True)
            return f"Error fetching course details: {str(e)}"

    tools.append(fetch_course_details)

    # 3. FAQs Tool (optimized)
    @tool("fetch_faqs", args_schema=FAQsInput)
    def fetch_faqs(query: Optional[str] = None, course_name: Optional[str] = None, top_k: int = 5) -> str:
        """Always use this tools to Fetch FAQs from database. Uses optimized search if query provided, otherwise returns top FAQs.
        
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
        """Always use this tool to Fetch professor/trainer information from database.
        
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
        """Always use this tool to Fetch company information from database.
        
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
    
    # 6. Search Courses Tool (optimized)
    @tool("search_courses", args_schema=SearchCoursesInput)
    def search_courses(search_term: str, limit: int = 10) -> str:
        """Always use this tool to Search for courses by name or description.
        
        Use this to find courses when user asks about available courses or searches for specific topics.
        
        Args:
            search_term: Search term (e.g., "tax", "accounting", "USA")
            limit: Maximum number of results (default: 10)
        
        Returns:
            List of matching courses with names and descriptions
        """
        try:
            courses = supabase_service.search_courses(search_term, limit=limit)
            
            if not courses:
                return f"No courses found matching '{search_term}'"
            
            formatted_courses = []
            for i, course in enumerate(courses, 1):
                parts = []
                if course.get("course_name"):
                    parts.append(f"Course: {course['course_name']}")
                if course.get("course_description"):
                    # Truncate long descriptions
                    desc = course['course_description']
                    if len(desc) > 200:
                        desc = desc[:200] + "..."
                    parts.append(f"Description: {desc}")
                if parts:
                    formatted_courses.append(f"{i}. " + " | ".join(parts))
            
            if formatted_courses:
                return "\n\n".join(formatted_courses)
            return f"No courses found matching '{search_term}'"
        
        except Exception as e:
            logger.error(f"Error searching courses: {e}", exc_info=True)
            return f"Error searching courses: {str(e)}"
    
    tools.append(search_courses)

    # 7. Save/Update Lead Data Tool (Supabase UPSERT operation)
    @tool("append_lead_data", args_schema=AppendLeadDataInput)
    def append_lead_data(
        name: Optional[str] = None,
        phone: Optional[str] = None,
        selected_course: Optional[str] = None,
        education_level: Optional[str] = None,
        goal: Optional[str] = None,
        notes: Optional[str] = None,
        add_timestamp: bool = True
    ) -> str:
        """CRITICAL: ALWAYS use this tool to SAVE or UPDATE lead data in Supabase database BEFORE sharing demo link.

        This tool performs UPSERT operation (CREATE new lead OR UPDATE existing lead).
        All parameters are optional, but you should pass ALL available information from the conversation.

        MANDATORY USAGE:
        - ALWAYS call this tool BEFORE sharing demo video link
        - Pass ALL collected data (name, course, education, goal, phone)
        - If some fields are missing/None, still call with available data
        - Minimum required: selected_course

        UPSERT LOGIC (Automatic):
        - Searches for existing lead by phone (if provided)
        - If not found by phone, searches by name (if provided)
        - If lead EXISTS → UPDATE (merge new data with existing, keeps old data)
        - If lead NOT EXISTS → CREATE (insert new lead)

        USE CASES:
        1. First time contact → Creates new lead
        2. Returning customer → Updates existing lead with new info
        3. Progressive data collection → Each call adds more info to same lead

        Args:
            name: Lead's name (if collected)
            phone: Lead's phone number (e.g., '03001234567') OR conversation_id from chat API (e.g., 'wa_1234567890'). This will be stored in the phone_number column in Supabase.
            selected_course: Course they selected (REQUIRED)
            education_level: Their education level (if collected)
            goal: Their goal/motivation (if collected)
            notes: Any additional notes
            add_timestamp: Always True (timestamp added automatically)

        Returns:
            Success/error message with lead ID and action (created/updated)

        Examples:
            CREATE (new lead):
            - append_lead_data(name="Hassan", phone="03001234567", selected_course="CTA", education_level="Bachelors", goal="Start tax consultancy", add_timestamp=True)
            - Returns: "✓ Lead data created successfully (ID: abc-123). You can now share the demo link."

            UPDATE (existing lead):
            - append_lead_data(phone="03001234567", notes="Interested in demo, will join next batch", add_timestamp=True)
            - Returns: "✓ Lead data updated successfully (ID: abc-123). You can now share the demo link."

            MINIMAL (just course):
            - append_lead_data(selected_course="CTA", add_timestamp=True)
            - Returns: "✓ Lead data created successfully (ID: def-456). You can now share the demo link."
        """
        try:
            result = supabase_service.append_lead_data(
                name=name,
                phone=phone,
                selected_course=selected_course,
                education_level=education_level,
                goal=goal,
                notes=notes,
                add_timestamp=add_timestamp
            )

            if result.get("status") == "success":
                action = result.get("action", "saved")
                lead_id = result.get("lead_id", "unknown")
                elapsed = result.get("elapsed_ms", 0)

                logger.info(f"✓ Lead data {action}: {lead_id} in {elapsed:.2f}ms")

                return f"✓ Lead data {action} successfully (ID: {lead_id}). You can now share the demo link."
            else:
                error_msg = result.get("message", "Unknown error")
                logger.error(f"Failed to save lead data: {error_msg}")
                return f"Error saving lead data: {error_msg}"

        except Exception as e:
            logger.error(f"Error in append_lead_data tool: {e}", exc_info=True)
            return f"Error saving lead data: {str(e)}"

    tools.append(append_lead_data)

    logger.info(f"Created {len(tools)} optimized Supabase tools (including lead data append)")
    return tools

