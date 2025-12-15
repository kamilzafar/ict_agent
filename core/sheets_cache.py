"""Google Sheets caching service with semantic search."""
import os
import json
import hashlib
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials as OAuth2Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import redis
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)


class GoogleSheetsCacheService:
    """Service for caching and searching Google Sheets data."""
    
    def __init__(
        self,
        credentials_path: Optional[str] = None,
        spreadsheet_id: Optional[str] = None,
        sheet_names: Optional[List[str]] = None,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_password: Optional[str] = None,
        redis_db: int = 0,
        chroma_db_path: str = "/app/sheets_index_db"
    ):
        """Initialize the Google Sheets cache service.
        
        Args:
            credentials_path: Path to Google service account credentials JSON
            spreadsheet_id: Google Sheets spreadsheet ID
            sheet_names: List of sheet names to cache
            redis_host: Redis host
            redis_port: Redis port
            redis_password: Redis password
            redis_db: Redis database number
            chroma_db_path: Path for ChromaDB index
        """
        # Configuration
        self.credentials_path = credentials_path or os.getenv("GOOGLE_SHEETS_CREDENTIALS_PATH")
        self.spreadsheet_id = spreadsheet_id or os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
        sheet_names_str = os.getenv("GOOGLE_SHEETS_SHEET_NAMES", "")
        self.sheet_names = sheet_names or [s.strip() for s in sheet_names_str.split(",") if s.strip()]
        
        # Check for OAuth2 credentials
        self.oauth2_client_id = os.getenv("GOOGLE_SHEETS_CLIENT_ID")
        self.oauth2_client_secret = os.getenv("GOOGLE_SHEETS_CLIENT_SECRET")
        self.oauth2_refresh_token = os.getenv("GOOGLE_SHEETS_REFRESH_TOKEN")
        
        # Validate configuration
        has_service_account = bool(self.credentials_path)
        has_oauth2 = bool(self.oauth2_client_id and self.oauth2_client_secret and self.oauth2_refresh_token)
        
        if not has_service_account and not has_oauth2:
            raise ValueError(
                "Either GOOGLE_SHEETS_CREDENTIALS_PATH (service account) or "
                "GOOGLE_SHEETS_CLIENT_ID/CLIENT_SECRET/REFRESH_TOKEN (OAuth2) must be set"
            )
        
        if not self.spreadsheet_id:
            raise ValueError("GOOGLE_SHEETS_SPREADSHEET_ID must be set")
        if not self.sheet_names:
            raise ValueError("GOOGLE_SHEETS_SHEET_NAMES must be set")
        
        # Log configuration for debugging
        logger.info(f"Google Sheets Configuration:")
        logger.info(f"  Spreadsheet ID: {self.spreadsheet_id}")
        logger.info(f"  Sheet Names: {', '.join(self.sheet_names)}")
        logger.info(f"  Auth Method: {'OAuth2' if has_oauth2 else 'Service Account' if has_service_account else 'None'}")
        
        # Initialize Google Sheets API
        self._init_google_sheets_client()
        
        # Initialize Redis with connection pooling and retry logic
        try:
            # Create Redis connection pool
            pool = redis.ConnectionPool(
                host=redis_host,
                port=redis_port,
                password=redis_password or os.getenv("REDIS_PASSWORD"),
                db=redis_db,
                max_connections=50,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30
            )
            self.redis_client = redis.Redis(connection_pool=pool)
            self.redis_client.ping()  # Test connection
            logger.info("Redis connection established")
        except redis.ConnectionError as e:
            logger.warning(f"Redis connection failed: {e}. Cache will use in-memory storage only.")
            self.redis_client = None
        except Exception as e:
            logger.warning(f"Redis initialization error: {e}. Cache will use in-memory storage only.")
            self.redis_client = None
        
        # Initialize embeddings and ChromaDB
        self.embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            dimensions=512
        )
        self.chroma_db_path = chroma_db_path
        self.vector_stores: Dict[str, Chroma] = {}
        
        # Initialize text splitter
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )
        
        # In-memory cache fallback (used when Redis is not available)
        self._in_memory_cache: Dict[str, List[List[str]]] = {}
        
        # Validate spreadsheet access and list available sheets
        try:
            logger.info(f"Validating access to spreadsheet: {self.spreadsheet_id}")
            available_sheets = self.list_available_sheets()
            logger.info(f"✓ Connected to spreadsheet {self.spreadsheet_id}")
            logger.info(f"✓ Available sheets: {', '.join(available_sheets)}")
            
            # Check if configured sheets exist
            missing_sheets = [s for s in self.sheet_names if s not in available_sheets]
            if missing_sheets:
                logger.error(
                    f"✗ Configured sheets not found: {', '.join(missing_sheets)}\n"
                    f"  Available sheets: {', '.join(available_sheets)}\n"
                    f"  Requested sheets: {', '.join(self.sheet_names)}\n"
                    f"  Please check sheet names match exactly (case-sensitive)"
                )
            else:
                logger.info(f"✓ All configured sheets found: {', '.join(self.sheet_names)}")
        except HttpError as e:
            if e.resp.status == 404:
                logger.error(
                    f"✗ Spreadsheet not found: {self.spreadsheet_id}\n"
                    f"  Error: {e}\n"
                    f"  Please verify:\n"
                    f"  1. Spreadsheet ID is correct\n"
                    f"  2. The Google account has access to this spreadsheet\n"
                    f"  3. The spreadsheet is not deleted or moved"
                )
            elif e.resp.status == 403:
                logger.error(
                    f"✗ Access denied to spreadsheet: {self.spreadsheet_id}\n"
                    f"  Error: {e}\n"
                    f"  Please verify:\n"
                    f"  1. The Google account has been granted access to the spreadsheet\n"
                    f"  2. For OAuth2: Share the sheet with the Google account email\n"
                    f"  3. For Service Account: Share the sheet with the service account email"
                )
            else:
                logger.error(f"✗ HTTP error accessing spreadsheet: {e}")
        except Exception as e:
            logger.error(f"✗ Could not validate spreadsheet access: {e}", exc_info=True)
        
        logger.info(f"Initialized Google Sheets cache service for {len(self.sheet_names)} sheets")
    
    def _init_google_sheets_client(self):
        """Initialize Google Sheets API client with OAuth2 or Service Account."""
        scopes = ['https://www.googleapis.com/auth/spreadsheets.readonly']
        credentials = None
        
        # Try OAuth2 first if credentials are available
        if self.oauth2_client_id and self.oauth2_client_secret and self.oauth2_refresh_token:
            try:
                logger.info("Attempting OAuth2 authentication...")
                credentials = OAuth2Credentials(
                    token=None,  # Will be refreshed
                    refresh_token=self.oauth2_refresh_token,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=self.oauth2_client_id,
                    client_secret=self.oauth2_client_secret,
                    scopes=scopes
                )
                # Refresh the token
                credentials.refresh(Request())
                logger.info("Google Sheets API client initialized with OAuth2")
            except Exception as e:
                logger.warning(f"OAuth2 authentication failed: {e}. Trying service account...")
                credentials = None
        
        # Fall back to service account if OAuth2 failed or not configured
        # Only try service account if credentials_path is set AND file exists
        if not credentials and self.credentials_path and os.path.exists(self.credentials_path):
            try:
                # Try to load as service account
                try:
                    credentials = service_account.Credentials.from_service_account_file(
                        self.credentials_path,
                        scopes=scopes
                    )
                    logger.info("Google Sheets API client initialized with service account")
                except Exception as sa_error:
                    # If service account fails, check if it's an OAuth2 client config file
                    try:
                        with open(self.credentials_path, 'r') as f:
                            cred_data = json.load(f)
                        
                        # Check if it's an OAuth2 client config (has "web" or "installed" key)
                        if "web" in cred_data or "installed" in cred_data:
                            logger.info("Found OAuth2 client config in credentials file")
                            client_config = cred_data.get("web") or cred_data.get("installed", {})
                            
                            if self.oauth2_refresh_token:
                                # Use refresh token if available
                                credentials = OAuth2Credentials(
                                    token=None,
                                    refresh_token=self.oauth2_refresh_token,
                                    token_uri=client_config.get("token_uri", "https://oauth2.googleapis.com/token"),
                                    client_id=client_config.get("client_id"),
                                    client_secret=client_config.get("client_secret"),
                                    scopes=scopes
                                )
                                credentials.refresh(Request())
                                logger.info("Google Sheets API client initialized with OAuth2 from file")
                            else:
                                raise ValueError(
                                    "OAuth2 client config found but GOOGLE_SHEETS_REFRESH_TOKEN is not set. "
                                    "Run 'python scripts/setup_oauth2.py' to get a refresh token."
                                )
                        else:
                            raise sa_error  # Re-raise original service account error
                    except json.JSONDecodeError:
                        raise sa_error  # Re-raise original service account error
            except Exception as e:
                logger.warning(f"Service account authentication failed: {e}")
                # Don't raise error here, let it fall through to check if we have any valid credentials
        
        # Final check: if no credentials were obtained, raise error
        if not credentials:
            raise RuntimeError(
                "No valid authentication method available. "
                "Configure either service account JSON or OAuth2 credentials."
            )
        
        # Build the service
        try:
            self.sheets_service = build('sheets', 'v4', credentials=credentials)
            logger.info("Google Sheets API service built successfully")
        except Exception as e:
            raise RuntimeError(f"Failed to build Google Sheets service: {e}") from e
    
    def _calculate_hash(self, data: List[List[str]]) -> str:
        """Calculate SHA256 hash of sheet data."""
        data_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()
    
    def _get_sheet_metadata(self, sheet_name: str) -> Optional[Dict[str, Any]]:
        """Get cached metadata for a sheet."""
        if not self.redis_client:
            return None
        
        try:
            key = f"sheets:metadata:{self.spreadsheet_id}:{sheet_name}"
            metadata_str = self.redis_client.get(key)
            if metadata_str:
                return json.loads(metadata_str)
        except Exception as e:
            logger.error(f"Error getting metadata for {sheet_name}: {e}")
        return None
    
    def _set_sheet_metadata(self, sheet_name: str, metadata: Dict[str, Any]):
        """Store metadata for a sheet."""
        if not self.redis_client:
            return
        
        try:
            key = f"sheets:metadata:{self.spreadsheet_id}:{sheet_name}"
            self.redis_client.set(key, json.dumps(metadata))
        except Exception as e:
            logger.error(f"Error setting metadata for {sheet_name}: {e}")
    
    def _get_cached_data(self, sheet_name: str) -> Optional[List[List[str]]]:
        """Get cached sheet data from Redis or in-memory cache."""
        # Try Redis first if available
        if self.redis_client:
            try:
                key = f"sheets:data:{self.spreadsheet_id}:{sheet_name}"
                data_str = self.redis_client.get(key)
                if data_str:
                    return json.loads(data_str)
            except Exception as e:
                logger.debug(f"Error getting cached data from Redis for {sheet_name}: {e}")
        
        # Fallback to in-memory cache
        if sheet_name in self._in_memory_cache:
            logger.debug(f"Retrieved {sheet_name} from in-memory cache")
            return self._in_memory_cache[sheet_name]
        
        return None
    
    def _set_cached_data(self, sheet_name: str, data: List[List[str]]):
        """Store sheet data in Redis cache and in-memory cache."""
        # Store in Redis if available
        if self.redis_client:
            try:
                key = f"sheets:data:{self.spreadsheet_id}:{sheet_name}"
                self.redis_client.setex(
                    key,
                    86400,  # 24 hours TTL
                    json.dumps(data)
                )
            except Exception as e:
                logger.debug(f"Error caching data in Redis for {sheet_name}: {e}")
        
        # Always store in in-memory cache as fallback
        self._in_memory_cache[sheet_name] = data
        logger.debug(f"Cached {sheet_name} in memory ({len(data)} rows)")
    
    def list_available_sheets(self) -> List[str]:
        """List all available sheet names in the spreadsheet."""
        try:
            logger.debug(f"Fetching spreadsheet metadata for: {self.spreadsheet_id}")
            spreadsheet = self.sheets_service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id
            ).execute()
            
            sheets = spreadsheet.get('sheets', [])
            if not sheets:
                logger.warning(f"No sheets found in spreadsheet {self.spreadsheet_id}")
                return []
            
            sheet_names = [
                sheet['properties']['title'] 
                for sheet in sheets
            ]
            logger.debug(f"Found {len(sheet_names)} sheets: {sheet_names}")
            return sheet_names
        except HttpError as e:
            if e.resp.status == 404:
                logger.error(
                    f"✗ Spreadsheet not found: {self.spreadsheet_id}\n"
                    f"  HTTP 404 Error: {e}\n"
                    f"  Check if spreadsheet ID is correct and the account has access."
                )
            elif e.resp.status == 403:
                logger.error(
                    f"✗ Access denied to spreadsheet: {self.spreadsheet_id}\n"
                    f"  HTTP 403 Error: {e}\n"
                    f"  Share the spreadsheet with the Google account or service account."
                )
            else:
                logger.error(f"✗ HTTP error listing sheets: {e}")
            raise
        except Exception as e:
            logger.error(f"✗ Error listing sheets: {e}", exc_info=True)
            raise
    
    def fetch_sheet_data(self, sheet_name: str) -> Tuple[List[List[str]], Dict[str, Any]]:
        """Fetch sheet data from Google Sheets API.
        
        Returns:
            Tuple of (data, metadata) where data is list of rows and metadata contains hash, timestamp, etc.
        """
        try:
            logger.debug(f"Fetching data from sheet '{sheet_name}' in spreadsheet {self.spreadsheet_id}")
            result = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=sheet_name
            ).execute()
            
            values = result.get('values', [])
            
            if not values:
                logger.warning(f"Sheet '{sheet_name}' is empty")
                return [], {
                    "hash": "",
                    "last_updated": datetime.now().isoformat(),
                    "row_count": 0,
                    "column_count": 0,
                    "sheet_name": sheet_name
                }
            
            # Calculate hash
            data_hash = self._calculate_hash(values)
            
            # Get metadata
            metadata = {
                "hash": data_hash,
                "last_updated": datetime.now().isoformat(),
                "row_count": len(values),
                "column_count": len(values[0]) if values else 0,
                "sheet_name": sheet_name
            }
            
            logger.info(f"✓ Fetched {len(values)} rows from {sheet_name}")
            return values, metadata
            
        except HttpError as e:
            if e.resp.status == 404:
                # Try to list available sheets for better error message
                try:
                    available_sheets = self.list_available_sheets()
                    logger.error(
                        f"✗ Sheet '{sheet_name}' not found in spreadsheet {self.spreadsheet_id}\n"
                        f"  Available sheets: {', '.join(available_sheets)}\n"
                        f"  Requested sheet: '{sheet_name}'\n"
                        f"  Check if sheet name matches exactly (case-sensitive)"
                    )
                except Exception as list_error:
                    logger.error(
                        f"✗ Sheet '{sheet_name}' not found and cannot list available sheets\n"
                        f"  Spreadsheet ID: {self.spreadsheet_id}\n"
                        f"  Error listing sheets: {list_error}\n"
                        f"  Original error: {e}"
                    )
            elif e.resp.status == 403:
                logger.error(
                    f"✗ Access denied when fetching sheet '{sheet_name}'\n"
                    f"  Spreadsheet ID: {self.spreadsheet_id}\n"
                    f"  Error: {e}\n"
                    f"  Verify the account has read access to this spreadsheet"
                )
            else:
                logger.error(f"✗ HTTP error fetching sheet '{sheet_name}': {e}")
            raise
        except Exception as e:
            logger.error(f"✗ Unexpected error fetching sheet '{sheet_name}': {e}", exc_info=True)
            raise
    
    def is_sheet_updated(self, sheet_name: str) -> bool:
        """Check if sheet has been updated without fetching full data.
        
        Returns:
            True if sheet needs to be synced, False if cache is current
        """
        try:
            # Get current metadata from Google Sheets (lightweight check)
            spreadsheet = self.sheets_service.spreadsheets().get(
                spreadsheetId=self.spreadsheet_id
            ).execute()
            
            # Find the sheet
            sheet_info = None
            for sheet in spreadsheet.get('sheets', []):
                if sheet['properties']['title'] == sheet_name:
                    sheet_info = sheet
                    break
            
            if not sheet_info:
                logger.warning(f"Sheet {sheet_name} not found")
                return False
            
            # Get cached metadata
            cached_metadata = self._get_sheet_metadata(sheet_name)
            if not cached_metadata:
                return True  # No cache, needs sync
            
            # For now, we'll do a full fetch to compare hash
            # In production, you could use revision history API for lighter check
            return True  # Always check by fetching and comparing hash
            
        except Exception as e:
            logger.error(f"Error checking if sheet {sheet_name} is updated: {e}")
            return True  # On error, assume needs sync
    
    def _create_documents_from_sheet(self, sheet_name: str, data: List[List[str]]) -> List[Document]:
        """Create Document objects from sheet data for indexing."""
        if not data:
            return []
        
        documents = []
        headers = data[0] if data else []
        
        # Process each row (skip header)
        for row_idx, row in enumerate(data[1:], start=2):  # Start at 2 (row 1 is header, row 2 is first data)
            # Create a text representation of the row
            row_text_parts = []
            for col_idx, value in enumerate(row):
                if col_idx < len(headers) and value:
                    header = headers[col_idx]
                    row_text_parts.append(f"{header}: {value}")
            
            if row_text_parts:
                row_text = " | ".join(row_text_parts)
                
                # Create metadata
                metadata = {
                    "sheet_name": sheet_name,
                    "row_number": row_idx,
                    "spreadsheet_id": self.spreadsheet_id
                }
                
                # Add header info to metadata
                for col_idx, header in enumerate(headers):
                    if col_idx < len(row):
                        metadata[f"col_{col_idx}"] = row[col_idx] if col_idx < len(row) else ""
                
                documents.append(Document(page_content=row_text, metadata=metadata))
        
        return documents
    
    def _index_sheet(self, sheet_name: str, data: List[List[str]]):
        """Index sheet data in ChromaDB for semantic search."""
        try:
            # Ensure directory exists with proper permissions
            import os
            os.makedirs(self.chroma_db_path, exist_ok=True)
            
            # Create documents from sheet data
            documents = self._create_documents_from_sheet(sheet_name, data)
            
            if not documents:
                logger.warning(f"No documents to index for {sheet_name}")
                return
            
            # Split documents if needed
            split_docs = []
            for doc in documents:
                splits = self.text_splitter.split_documents([doc])
                split_docs.extend(splits)
            
            # Create or update ChromaDB collection
            collection_name = f"{sheet_name}_index"
            
            # Try to delete existing collection if it exists
            if collection_name in self.vector_stores:
                try:
                    self.vector_stores[collection_name].delete_collection()
                except Exception as e:
                    logger.debug(f"Could not delete existing collection {collection_name}: {e}")
            
            # Try to create/update collection with retry logic for concurrent access
            max_retries = 3
            retry_delay = 1.0
            
            for attempt in range(max_retries):
                try:
                    # Create new collection
                    self.vector_stores[collection_name] = Chroma.from_documents(
                        documents=split_docs,
                        embedding=self.embeddings,
                        persist_directory=self.chroma_db_path,
                        collection_name=collection_name
                    )
                    
                    logger.info(f"Indexed {len(split_docs)} documents for {sheet_name}")
                    return  # Success
                    
                except Exception as e:
                    error_msg = str(e).lower()
                    # Check if it's a database locking error
                    if "unable to open database" in error_msg or "database is locked" in error_msg or "code: 14" in error_msg:
                        if attempt < max_retries - 1:
                            logger.warning(
                                f"Database locked while indexing {sheet_name} (attempt {attempt + 1}/{max_retries}). "
                                f"Retrying in {retry_delay}s..."
                            )
                            import time
                            time.sleep(retry_delay)
                            retry_delay *= 2  # Exponential backoff
                            continue
                        else:
                            logger.error(
                                f"Error indexing sheet {sheet_name}: Database is locked after {max_retries} attempts. "
                                f"This is normal when multiple workers are starting. The index will be created on next sync."
                            )
                            return  # Give up after max retries
                    else:
                        # Other errors - log and return
                        logger.error(f"Error indexing sheet {sheet_name}: {e}")
                        return
            
        except Exception as e:
            logger.error(f"Error indexing sheet {sheet_name}: {e}")
    
    def sync_sheet(self, sheet_name: str) -> bool:
        """Sync a specific sheet - fetch if changed, update cache.
        
        Returns:
            True if sheet was updated, False if no changes
        """
        try:
            # Fetch current data
            data, new_metadata = self.fetch_sheet_data(sheet_name)
            
            # Get cached metadata
            cached_metadata = self._get_sheet_metadata(sheet_name)
            
            # Check if data changed
            if cached_metadata and cached_metadata.get("hash") == new_metadata["hash"]:
                logger.debug(f"No changes detected for {sheet_name}")
                return False
            
            # Data changed - update cache
            logger.info(f"Updating cache for {sheet_name}")
            
            # Store in Redis
            self._set_cached_data(sheet_name, data)
            self._set_sheet_metadata(sheet_name, new_metadata)
            
            # Re-index in ChromaDB
            self._index_sheet(sheet_name, data)
            
            logger.info(f"Successfully synced {sheet_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error syncing sheet {sheet_name}: {e}")
            raise
    
    def preload_all_sheets(self):
        """Pre-load all configured sheets on startup."""
        logger.info(f"Pre-loading {len(self.sheet_names)} sheets...")
        
        for sheet_name in self.sheet_names:
            try:
                logger.info(f"Pre-loading {sheet_name}...")
                self.sync_sheet(sheet_name)
            except Exception as e:
                logger.error(f"Error pre-loading {sheet_name}: {e}")
                # Continue with other sheets
        
        logger.info("Pre-loading complete")
    
    def search_cached_data(self, query: str, sheet_name: Optional[str] = None, top_k: int = 5) -> List[Document]:
        """Search cached sheet data using semantic search.
        
        Args:
            query: Search query
            sheet_name: Optional sheet name to search (searches all if None)
            top_k: Number of results to return
        
        Returns:
            List of relevant documents
        """
        results = []
        
        sheets_to_search = [sheet_name] if sheet_name else self.sheet_names
        
        for sheet in sheets_to_search:
            collection_name = f"{sheet}_index"
            
            if collection_name not in self.vector_stores:
                # Try to load existing collection
                try:
                    self.vector_stores[collection_name] = Chroma(
                        persist_directory=self.chroma_db_path,
                        embedding_function=self.embeddings,
                        collection_name=collection_name
                    )
                except:
                    logger.warning(f"Collection {collection_name} not found, skipping")
                    continue
            
            try:
                vector_store = self.vector_stores[collection_name]
                docs = vector_store.similarity_search(query, k=top_k)
                results.extend(docs)
            except Exception as e:
                logger.error(f"Error searching {sheet}: {e}")
        
        # Sort by relevance and return top_k
        return results[:top_k]
    
    def get_sheet_data(self, sheet_name: str) -> Optional[List[List[str]]]:
        """Get sheet data from cache (no API call).
        
        Returns:
            Sheet data as list of rows, or None if not cached
        """
        return self._get_cached_data(sheet_name)
    
    def get_all_sheets_data(self) -> Dict[str, List[List[str]]]:
        """Get all cached sheet data.
        
        Returns:
            Dictionary mapping sheet names to their data
        """
        result = {}
        for sheet_name in self.sheet_names:
            data = self._get_cached_data(sheet_name)
            if data:
                result[sheet_name] = data
        return result

