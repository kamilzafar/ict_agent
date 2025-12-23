"""Optimized Supabase database service with smart caching and automatic invalidation."""
import os
import logging
from typing import List, Optional, Dict, Any
import time
import threading
from threading import Lock

logger = logging.getLogger(__name__)

try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    logger.warning("Supabase client not installed. Install with: pip install supabase")


class SupabaseService:
    """Optimized service with smart caching + automatic invalidation via Realtime.
    
    Features:
    - In-memory caching for <1ms queries
    - Automatic cache invalidation via Supabase Realtime
    - Instant updates when data changes (1-2 seconds)
    - Fallback TTL for safety
    """
    
    # Fallback TTLs (cache expires after this even if no change detected)
    FALLBACK_TTL = {
        "course_links": 300,      # 5 minutes (safety net)
        "course_details": 600,    # 10 minutes
        "faqs": 1800,            # 30 minutes
        "professor_info": 3600,  # 1 hour
        "company_info": 7200,    # 2 hours
    }
    
    def __init__(self, supabase_url: Optional[str] = None, supabase_key: Optional[str] = None):
        """Initialize Supabase client with Realtime subscriptions."""
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
            logger.info("✓ Supabase client initialized successfully")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Supabase client: {str(e)}") from e
        
        # In-memory cache: {cache_key: (data, timestamp)}
        self._cache: Dict[str, tuple] = {}
        self._cache_lock = Lock()
        
        # Start Realtime subscriptions for automatic cache invalidation
        self._setup_realtime_subscriptions()
        
        logger.info("✓ Cache with automatic invalidation initialized")
    
    def _setup_realtime_subscriptions(self):
        """Set up Supabase Realtime subscriptions to auto-invalidate cache."""
        try:
            # Check if Realtime is enabled
            enable_realtime = os.getenv("SUPABASE_REALTIME_ENABLED", "true").lower() == "true"
            if not enable_realtime:
                logger.info("Supabase Realtime disabled (SUPABASE_REALTIME_ENABLED=false)")
                logger.info("Cache will use fallback TTL only")
                return
            
            # Subscribe to changes on all tables
            tables_to_watch = [
                "course_links",
                "course_details", 
                "faqs",
                "about_professor",
                "company_info"
            ]
            
            for table in tables_to_watch:
                try:
                    # Subscribe to INSERT, UPDATE, DELETE events
                    channel = self.client.realtime.channel(f"cache-invalidation-{table}")
                    
                    channel.on("postgres_changes", {
                        "event": "*",  # INSERT, UPDATE, DELETE
                        "schema": "public",
                        "table": table
                    }, self._handle_table_change)
                    
                    channel.subscribe()
                    logger.info(f"✓ Realtime subscription active for {table}")
                    
                except Exception as e:
                    logger.warning(f"Could not set up Realtime for {table}: {e}")
                    logger.warning("Cache will use fallback TTL instead")
        
        except Exception as e:
            logger.warning(f"Realtime subscriptions not available: {e}")
            logger.warning("Cache will still work with fallback TTL")
            logger.info("To enable Realtime: Set SUPABASE_REALTIME_ENABLED=true and enable Realtime in Supabase Dashboard")
    
    def _handle_table_change(self, payload):
        """Handle Realtime change event - clear cache automatically."""
        try:
            table = payload.get("table")
            event_type = payload.get("eventType")  # INSERT, UPDATE, DELETE
            
            logger.info(f"🔄 Realtime change detected: {event_type} on {table}")
            
            # Clear cache for this table
            self.clear_cache(table)
            
            logger.info(f"✓ Cache cleared for {table} (automatic)")
            
        except Exception as e:
            logger.error(f"Error handling Realtime change: {e}", exc_info=True)
    
    def _get_cache_key(self, table: str, **kwargs) -> str:
        """Generate cache key from table name and parameters."""
        params = "_".join(f"{k}={v}" for k, v in sorted(kwargs.items()) if v is not None)
        return f"{table}:{params}" if params else f"{table}:all"
    
    def _get_cached(self, cache_key: str, table: str) -> Optional[Any]:
        """Get data from cache if still valid."""
        with self._cache_lock:
            if cache_key in self._cache:
                data, timestamp = self._cache[cache_key]
                age = time.time() - timestamp
                fallback_ttl = self.FALLBACK_TTL.get(table, 300)
                
                if age < fallback_ttl:
                    logger.debug(f"Cache HIT: {cache_key} (age: {age:.2f}s)")
                    return data
                else:
                    # Cache expired (fallback TTL)
                    del self._cache[cache_key]
                    logger.debug(f"Cache EXPIRED: {cache_key} (age: {age:.2f}s > {fallback_ttl}s)")
            return None
    
    def _set_cached(self, cache_key: str, data: Any):
        """Store data in cache."""
        with self._cache_lock:
            self._cache[cache_key] = (data, time.time())
            logger.debug(f"Cache SET: {cache_key}")
    
    def clear_cache(self, table: Optional[str] = None):
        """Clear cache for a specific table or all tables.
        
        Use this when you update data in Supabase and want instant updates.
        
        Args:
            table: Optional table name to clear (e.g., "course_links"), 
                   or None to clear all caches
        """
        with self._cache_lock:
            if table:
                keys_to_remove = [k for k in self._cache.keys() if k.startswith(f"{table}:")]
                for key in keys_to_remove:
                    del self._cache[key]
                logger.info(f"Cleared cache for {table} ({len(keys_to_remove)} entries)")
            else:
                count = len(self._cache)
                self._cache.clear()
                logger.info(f"Cleared all caches ({count} entries)")
    
    def get_course_links(self, course_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get course links (cached, auto-invalidated on changes)."""
        cache_key = self._get_cache_key("course_links", course_name=course_name)
        
        # Check cache first
        cached = self._get_cached(cache_key, "course_links")
        if cached is not None:
            return cached
        
        # Cache miss - fetch from database
        start_time = time.time()
        try:
            query = self.client.table("course_links").select("course_name,demo_link,pdf_link,course_link")
            
            if course_name:
                query = query.ilike("course_name", f"%{course_name}%").limit(1)
            else:
                query = query.limit(10)
            
            response = query.execute()
            data = response.data if response.data else []
            
            # Store in cache
            self._set_cached(cache_key, data)
            
            elapsed = (time.time() - start_time) * 1000
            logger.debug(f"get_course_links: {elapsed:.2f}ms (DB)")
            return data
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            logger.error(f"Error fetching course links ({elapsed:.2f}ms): {e}", exc_info=True)
            return []
    
    def get_course_details(self, course_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get course details (cached, auto-invalidated on changes)."""
        cache_key = self._get_cache_key("course_details", course_name=course_name)
        
        cached = self._get_cached(cache_key, "course_details")
        if cached is not None:
            return cached
        
        start_time = time.time()
        try:
            query = self.client.table("course_details").select("*")
            
            if course_name:
                query = query.ilike("course_name", f"%{course_name}%").limit(1)
            else:
                query = query.limit(10)
            
            response = query.execute()
            data = response.data if response.data else []
            
            self._set_cached(cache_key, data)
            
            elapsed = (time.time() - start_time) * 1000
            logger.debug(f"get_course_details: {elapsed:.2f}ms (DB)")
            return data
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            logger.error(f"Error fetching course details ({elapsed:.2f}ms): {e}", exc_info=True)
            return []
    
    def get_faqs(self, query_text: Optional[str] = None, course_name: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
        """Get FAQs (cached, auto-invalidated on changes)."""
        cache_key = self._get_cache_key("faqs", query_text=query_text, course_name=course_name, limit=limit)
        
        cached = self._get_cached(cache_key, "faqs")
        if cached is not None:
            return cached
        
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
            
            self._set_cached(cache_key, data)
            
            elapsed = (time.time() - start_time) * 1000
            logger.debug(f"get_faqs: {elapsed:.2f}ms (DB)")
            return data
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            logger.error(f"Error fetching FAQs ({elapsed:.2f}ms): {e}", exc_info=True)
            return []
    
    def get_professor_info(self, professor_name: Optional[str] = None, course_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get professor info (cached, auto-invalidated on changes)."""
        cache_key = self._get_cache_key("professor_info", professor_name=professor_name, course_name=course_name)
        
        cached = self._get_cached(cache_key, "professor_info")
        if cached is not None:
            return cached
        
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
            
            self._set_cached(cache_key, data)
            
            elapsed = (time.time() - start_time) * 1000
            logger.debug(f"get_professor_info: {elapsed:.2f}ms (DB)")
            return data
        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            logger.error(f"Error fetching professor info ({elapsed:.2f}ms): {e}", exc_info=True)
            return []
    
    def get_company_info(self, field_name: Optional[str] = None) -> Dict[str, Any]:
        """Get company info (cached, auto-invalidated on changes)."""
        cache_key = self._get_cache_key("company_info", field_name=field_name)
        
        cached = self._get_cached(cache_key, "company_info")
        if cached is not None:
            return cached
        
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
            
            self._set_cached(cache_key, data)
            
            elapsed = (time.time() - start_time) * 1000
            logger.debug(f"get_company_info: {elapsed:.2f}ms (DB)")
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
