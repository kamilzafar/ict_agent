"""Supabase database service - direct database calls, no caching."""
import os
import logging
from typing import List, Optional, Dict, Any
import time

logger = logging.getLogger(__name__)

try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    logger.warning("Supabase client not installed. Install with: pip install supabase")


class SupabaseService:
    """Supabase service with direct database calls - no caching.
    
    All queries go directly to the database for real-time data.
    """
    
    def __init__(self, supabase_url: Optional[str] = None, supabase_key: Optional[str] = None):
        """Initialize Supabase client."""
        if not SUPABASE_AVAILABLE:
            raise ImportError("Supabase client not installed. Install with: pip install supabase")
        
        self.supabase_url = supabase_url or os.getenv("SUPABASE_URL")
        self.supabase_key = supabase_key or os.getenv("SUPABASE_KEY")
        
        if not self.supabase_url or not self.supabase_key:
            raise ValueError(
                "Supabase credentials not found. Please set SUPABASE_URL and SUPABASE_KEY environment variables."
            )
        
        try:
            self.client: Client = create_client(self.supabase_url, self.supabase_key)
            logger.info("✓ Supabase client initialized successfully (no caching - direct DB calls)")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Supabase client: {str(e)}") from e
    
    def clear_cache(self, table: Optional[str] = None):
        """Clear cache endpoint - kept for API compatibility, but no-op since caching is disabled.
        
        Args:
            table: Optional table name (ignored - no cache to clear)
        """
        logger.debug("clear_cache called but caching is disabled - no action taken")
    
    def get_course_links(self, course_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get course links - direct database call, no caching."""
        start_time = time.time()
        try:
            query = self.client.table("course_links").select("course_name,demo_link,pdf_link,course_link")
            
            if course_name:
                query = query.ilike("course_name", f"%{course_name}%").limit(1)
            else:
                query = query.limit(10)
            
            response = query.execute()
            data = response.data if response.data else []
            
            elapsed = (time.time() - start_time) * 1000
            logger.debug(f"get_course_links: {elapsed:.2f}ms (direct DB)")
            return data
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            logger.error(f"Error fetching course links ({elapsed:.2f}ms): {e}", exc_info=True)
            return []
    
    def get_course_details(self, course_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get course details - direct database call, no caching."""
        start_time = time.time()
        try:
            query = self.client.table("course_details").select("*")
            
            if course_name:
                query = query.ilike("course_name", f"%{course_name}%").limit(1)
            else:
                query = query.limit(10)
            
            response = query.execute()
            data = response.data if response.data else []
            
            elapsed = (time.time() - start_time) * 1000
            logger.debug(f"get_course_details: {elapsed:.2f}ms (direct DB)")
            return data
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            logger.error(f"Error fetching course details ({elapsed:.2f}ms): {e}", exc_info=True)
            return []
    
    def get_faqs(self, query_text: Optional[str] = None, course_name: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
        """Get FAQs - direct database call, no caching."""
        start_time = time.time()
        try:
            query = self.client.table("faqs").select("faq,course_name,question,answer")
            
            if course_name:
                query = query.ilike("course_name", f"%{course_name}%")
            
            if query_text:
                query = query.or_(f"question.ilike.%{query_text}%,answer.ilike.%{query_text}%")
            
            query = query.limit(limit)
            response = query.execute()
            data = response.data if response.data else []
            
            elapsed = (time.time() - start_time) * 1000
            logger.debug(f"get_faqs: {elapsed:.2f}ms (direct DB)")
            return data
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            logger.error(f"Error fetching FAQs ({elapsed:.2f}ms): {e}", exc_info=True)
            return []
    
    def get_professor_info(self, professor_name: Optional[str] = None, course_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get professor info - direct database call, no caching."""
        start_time = time.time()
        try:
            query = self.client.table("about_professor").select("*")
            
            if professor_name:
                query = query.ilike("full_name", f"%{professor_name}%").limit(5)
            elif course_name:
                query = query.ilike("courses_currently_teaching", f"%{course_name}%").limit(5)
            else:
                query = query.limit(10)
            
            response = query.execute()
            data = response.data if response.data else []
            
            elapsed = (time.time() - start_time) * 1000
            logger.debug(f"get_professor_info: {elapsed:.2f}ms (direct DB)")
            return data
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            logger.error(f"Error fetching professor info ({elapsed:.2f}ms): {e}", exc_info=True)
            return []
    
    def get_company_info(self, field_name: Optional[str] = None) -> Dict[str, Any]:
        """Get company info - direct database call, no caching."""
        start_time = time.time()
        try:
            query = self.client.table("company_info").select("field_name,field_value,notes")
            
            if field_name:
                query = query.eq("field_name", field_name).limit(1)
            else:
                query = query.limit(100)
            
            response = query.execute()
            
            if response.data:
                if field_name:
                    if len(response.data) > 0:
                        data = {response.data[0]["field_name"]: response.data[0]["field_value"]}
                    else:
                        data = {}
                else:
                    data = {row["field_name"]: row["field_value"] for row in response.data if row.get("field_name")}
            else:
                data = {}
            
            elapsed = (time.time() - start_time) * 1000
            logger.debug(f"get_company_info: {elapsed:.2f}ms (direct DB)")
            return data
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            logger.error(f"Error fetching company info ({elapsed:.2f}ms): {e}", exc_info=True)
            return {}
    
    def search_courses(self, search_term: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search courses (no cache - always fresh)."""
        start_time = time.time()
        try:
            query = self.client.table("course_details").select("course_name,course_description")
            if search_term:
                query = query.or_(
                    f"course_name.ilike.%{search_term}%,course_description.ilike.%{search_term}%"
                ).limit(limit)
            else:
                query = query.limit(limit)
            
            response = query.execute()
            elapsed = (time.time() - start_time) * 1000
            logger.debug(f"search_courses: {elapsed:.2f}ms")
            return response.data if response.data else []
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            logger.error(f"Error searching courses ({elapsed:.2f}ms): {e}", exc_info=True)
            return []

    def append_lead_data(
        self,
        name: Optional[str] = None,
        phone: Optional[str] = None,
        selected_course: Optional[str] = None,
        education_level: Optional[str] = None,
        goal: Optional[str] = None,
        notes: Optional[str] = None,
        add_timestamp: bool = False
    ) -> Dict[str, Any]:
        """Append or update lead data in Supabase - direct database call, no caching.

        This method will:
        1. Search for existing lead by phone or name
        2. If found, UPDATE the existing record (merge new data with existing)
        3. If not found, INSERT a new record

        Args:
            name: Lead's name
            phone: Lead's phone number
            selected_course: Course they're interested in
            education_level: Their education level
            goal: Their goal/motivation
            notes: Additional notes
            add_timestamp: Whether to add timestamp (always added automatically)

        Returns:
            Dict with status and message
        """
        start_time = time.time()

        try:
            from datetime import datetime

            # Build data dict (only include provided fields)
            data = {}
            if name:
                data['name'] = name
            if phone:
                data['phone'] = phone
            if selected_course:
                data['selected_course'] = selected_course
            if education_level:
                data['education_level'] = education_level
            if goal:
                data['goal'] = goal
            if notes:
                data['notes'] = notes

            # Always add timestamp
            data['timestamp'] = datetime.now().isoformat()

            # If no data provided, return error
            if len(data) == 1:  # Only timestamp
                return {
                    "status": "error",
                    "message": "No lead data provided. Please provide at least one field (name, phone, course, etc.)"
                }

            # Try to find existing lead by phone or name
            existing_lead = None

            if phone:
                # Search by phone first (most unique identifier)
                query = self.client.table("leads").select("*").eq("phone", phone).limit(1)
                response = query.execute()
                if response.data:
                    existing_lead = response.data[0]

            if not existing_lead and name:
                # Search by name if phone not provided or not found
                query = self.client.table("leads").select("*").ilike("name", name).limit(1)
                response = query.execute()
                if response.data:
                    existing_lead = response.data[0]

            if existing_lead:
                # UPDATE existing lead (merge new data)
                lead_id = existing_lead['id']

                # Merge with existing data (new data overwrites old)
                update_data = {**existing_lead, **data}

                # Remove 'id' from update data (can't update primary key)
                update_data.pop('id', None)
                update_data.pop('created_at', None)  # Don't update created_at

                response = self.client.table("leads").update(update_data).eq("id", lead_id).execute()

                elapsed = (time.time() - start_time) * 1000
                logger.info(f"✓ Updated lead {lead_id} in {elapsed:.2f}ms")

                return {
                    "status": "success",
                    "action": "updated",
                    "message": f"Lead data updated successfully for {name or phone or 'lead'}",
                    "lead_id": lead_id,
                    "elapsed_ms": elapsed
                }
            else:
                # INSERT new lead
                response = self.client.table("leads").insert(data).execute()

                if response.data:
                    lead_id = response.data[0].get('id')
                    elapsed = (time.time() - start_time) * 1000
                    logger.info(f"✓ Created new lead {lead_id} in {elapsed:.2f}ms")

                    return {
                        "status": "success",
                        "action": "created",
                        "message": f"New lead created successfully for {name or phone or 'lead'}",
                        "lead_id": lead_id,
                        "elapsed_ms": elapsed
                    }
                else:
                    elapsed = (time.time() - start_time) * 1000
                    logger.error(f"Failed to create lead: no data returned ({elapsed:.2f}ms)")
                    return {
                        "status": "error",
                        "message": "Failed to create lead in database"
                    }

        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            logger.error(f"Error appending lead data ({elapsed:.2f}ms): {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"Error saving lead data: {str(e)}"
            }
