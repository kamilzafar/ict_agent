"""Long-term memory system for the agent using vector store."""
import os
import threading
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import json
import hashlib

logger = logging.getLogger(__name__)

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter


class LongTermMemory:
    """Manages long-term memory using ChromaDB vector store."""
    
    def __init__(self, persist_directory: str = "/app/memory_db", collection_name: str = "conversations"):
        """Initialize the memory system.
        
        Args:
            persist_directory: Directory to persist the vector store
            collection_name: Name of the ChromaDB collection
        """
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        os.makedirs(persist_directory, exist_ok=True)
        
        # Initialize embeddings using OpenAI (required)
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY environment variable is required. "
                "Please set it in your .env file or environment variables."
            )
        
        try:
            self.embeddings = OpenAIEmbeddings(openai_api_key=api_key)
        except Exception as e:
            raise RuntimeError(
                f"Failed to initialize OpenAI embeddings: {str(e)}. "
                "Please check your OPENAI_API_KEY is valid."
            ) from e
        
        # Initialize vector store with persistence
        # ChromaDB persists to disk automatically when persist_directory is set
        try:
            self.vectorstore = Chroma(
                persist_directory=persist_directory,
                collection_name=collection_name,
                embedding_function=self.embeddings
            )
            logger.info(f"✓ ChromaDB initialized: {persist_directory}/{collection_name}")
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}", exc_info=True)
            raise RuntimeError(f"Failed to initialize ChromaDB vector store: {str(e)}") from e
        
        # Text splitter for chunking conversations
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
        )
        
        # Store conversation metadata
        self.metadata_file = os.path.join(persist_directory, "conversations_metadata.json")
        self.conversations_metadata = self._load_metadata()
        logger.info(f"✓ Loaded {len(self.conversations_metadata)} conversations from metadata file")
        logger.debug(f"Metadata file: {self.metadata_file}")
        
        # Thread-safety locks
        self._metadata_lock = threading.Lock()  # For metadata operations
        self._file_lock = threading.Lock()  # For file I/O operations
        
        # Production settings
        self.max_turns_in_metadata = 100  # Only keep last 100 turns in metadata to prevent bloat

        # Stage tracking
        self.STAGES = {
            "NEW": "Just started conversation",
            "NAME_COLLECTED": "Got their name",
            "COURSE_SELECTED": "They selected a course",
            "EDUCATION_COLLECTED": "Got education level",
            "GOAL_COLLECTED": "Got their goals/motivation",
            "DEMO_SHARED": "Demo video shared",
            "ENROLLED": "Successfully enrolled",
            "LOST": "Lead went cold / not interested"
        }
        self.STAGE_ORDER = ["NEW", "NAME_COLLECTED", "COURSE_SELECTED",
                           "EDUCATION_COLLECTED", "GOAL_COLLECTED", "DEMO_SHARED", "ENROLLED"]
    
    def _load_metadata(self) -> Dict[str, Any]:
        """Load conversation metadata from disk."""
        if os.path.exists(self.metadata_file):
            try:
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}
    
    def _save_metadata(self):
        """Save conversation metadata to disk (thread-safe with atomic writes)."""
        import sys
        import time

        with self._file_lock:
            # Create a copy to avoid holding lock during I/O
            try:
                metadata_copy = json.dumps(self.conversations_metadata, indent=2, ensure_ascii=False)
            except Exception as e:
                # If serialization fails, log and skip
                import logging
                logging.error(f"Failed to serialize metadata: {e}")
                return

            # Atomic write using temp file + rename pattern
            temp_file = self.metadata_file + ".tmp"
            try:
                # Write to temp file
                with open(temp_file, 'w', encoding='utf-8') as f:
                    f.write(metadata_copy)

                # Windows-compatible atomic replace with retry logic
                max_retries = 3
                retry_delay = 0.1

                for attempt in range(max_retries):
                    try:
                        # On Windows, os.replace can fail if file is locked
                        # Try to remove the old file first, then rename
                        if sys.platform == "win32" and os.path.exists(self.metadata_file):
                            # Windows-specific: remove then rename
                            try:
                                os.remove(self.metadata_file)
                            except PermissionError:
                                # File might be locked, wait and retry
                                if attempt < max_retries - 1:
                                    time.sleep(retry_delay * (attempt + 1))
                                    continue
                                else:
                                    raise
                            os.rename(temp_file, self.metadata_file)
                        else:
                            # Unix-like systems: atomic replace
                            os.replace(temp_file, self.metadata_file)

                        # Success - break out of retry loop
                        break

                    except (PermissionError, OSError) as e:
                        if attempt < max_retries - 1:
                            # Wait before retry
                            time.sleep(retry_delay * (attempt + 1))
                            continue
                        else:
                            # Final attempt failed
                            raise

            except Exception as e:
                # Clean up temp file on error
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except Exception:
                        pass
                import logging
                logging.error(f"Failed to save metadata: {e}")

                # Don't raise the error - just log it
                # This prevents the entire chat request from failing
                # The data is still in memory, will be saved on next successful write
                logging.warning("Metadata save failed, but data is preserved in memory")
    
    def add_conversation(
        self,
        user_message: str,
        assistant_message: str,
        conversation_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        embed: bool = False
    ):
        """Add a conversation turn to memory.
        
        PRODUCTION OPTIMIZATION: By default, do NOT embed individual turns.
        Only embed summaries to reduce API calls and costs.
        
        Args:
            user_message: User's message
            assistant_message: Assistant's response
            conversation_id: Unique identifier for the conversation
            metadata: Additional metadata to store
            embed: Whether to embed this turn (default: False for production efficiency)
        """
        timestamp = datetime.now().isoformat()
        
        # Update conversation metadata (lightweight, no embedding) - thread-safe
        with self._metadata_lock:
            if conversation_id not in self.conversations_metadata:
                # Initialize with stage tracking structure
                self._initialize_conversation_metadata(conversation_id)

            # Add turn to metadata
            self.conversations_metadata[conversation_id]["turns"].append({
                "timestamp": timestamp,
                "user_message": user_message,
                "assistant_message": assistant_message
            })
            
            # Limit metadata size to prevent bloat (keep only recent turns)
            turns = self.conversations_metadata[conversation_id]["turns"]
            if len(turns) > self.max_turns_in_metadata:
                # Keep only the most recent turns
                self.conversations_metadata[conversation_id]["turns"] = turns[-self.max_turns_in_metadata:]
        
        # Only embed if explicitly requested (for production, we skip this)
        if embed:
            conversation_text = f"User: {user_message}\nAssistant: {assistant_message}"
            doc_metadata = {
                "conversation_id": conversation_id,
                "timestamp": timestamp,
                "type": "conversation_turn",
                **(metadata or {})
            }
            
            chunks = self.text_splitter.split_text(conversation_text)
            documents = [
                Document(
                    page_content=chunk,
                    metadata={**doc_metadata, "chunk_index": i}
                )
                for i, chunk in enumerate(chunks)
            ]
            self.vectorstore.add_documents(documents)
        
        # Save metadata (debounced - could be optimized further with async writes)
        self._save_metadata()
    
    def add_summary(self, conversation_id: str, summary: str, replace_old: bool = True):
        """Add or update a summary for a conversation.
        
        PRODUCTION: Only summaries are embedded, not individual turns.
        This reduces API calls significantly for 10k+ message conversations.
        
        Args:
            conversation_id: Unique identifier for the conversation
            summary: Summary text
            replace_old: If True, replace old summary in vector store (default: True)
        """
        timestamp = datetime.now().isoformat()
        
        # Thread-safe metadata update
        with self._metadata_lock:
            if conversation_id not in self.conversations_metadata:
                self.conversations_metadata[conversation_id] = {
                    "created_at": timestamp,
                    "turns": [],
                    "summary": summary
                }
            else:
                self.conversations_metadata[conversation_id]["summary"] = summary
        
        # Embed summary for retrieval (this is the only thing we embed)
        summary_doc = Document(
            page_content=f"Conversation Summary: {summary}",
            metadata={
                "conversation_id": conversation_id,
                "timestamp": timestamp,
                "type": "summary"
            }
        )
        
        if replace_old:
            # Remove old summary documents for this conversation
            try:
                # ChromaDB doesn't have direct delete by metadata, so we add new one
                # Old ones will be filtered out in search by timestamp
                pass
            except Exception:
                pass  # Continue even if cleanup fails
        
        # Add new summary to vector store
        self.vectorstore.add_documents([summary_doc])
        self._save_metadata()
    
    def search_relevant_context(
        self,
        query: str,
        k: int = 5,
        conversation_id: Optional[str] = None
    ) -> List[Document]:
        """Search for relevant context from memory.
        
        Direct database calls - no caching. Searches both ChromaDB summaries and conversation history.
        
        Args:
            query: Search query
            k: Number of results to return
            conversation_id: Optional conversation ID to filter by
        
        Returns:
            List of relevant documents
        """
        results = []
        
        # 1. Search ChromaDB summaries (direct API call, no cache)
        search_k = k * 3 if conversation_id else k * 2
        
        try:
            vector_results = self.vectorstore.similarity_search(query, k=search_k)
            
            # Filter by conversation_id and type
            for doc in vector_results:
                doc_type = doc.metadata.get("type")
                doc_conv_id = doc.metadata.get("conversation_id")
                
                # Only include summaries
                if doc_type != "summary":
                    continue
                
                # Filter by conversation_id if provided
                if conversation_id and doc_conv_id != conversation_id:
                    continue
                
                results.append(doc)
                if len(results) >= k:
                    break
        except Exception as e:
            logger.warning(f"ChromaDB search failed: {e}")
        
        # 2. If conversation_id provided and we don't have enough results,
        # search conversation history (for conversations without summaries yet)
        if conversation_id and len(results) < k:
            try:
                # Get conversation history directly
                history = self.get_conversation_history(conversation_id)
                
                # Simple text matching in conversation history
                query_lower = query.lower()
                for turn in history:
                    user_msg = turn.get("user_message", "").lower()
                    assistant_msg = turn.get("assistant_message", "").lower()
                    
                    # Check if query matches in this turn
                    if query_lower in user_msg or query_lower in assistant_msg:
                        # Create a Document from the conversation turn
                        turn_text = f"User: {turn.get('user_message', '')}\nAssistant: {turn.get('assistant_message', '')}"
                        doc = Document(
                            page_content=turn_text,
                            metadata={
                                "conversation_id": conversation_id,
                                "timestamp": turn.get("timestamp", ""),
                                "type": "conversation_turn"
                            }
                        )
                        results.append(doc)
                        
                        if len(results) >= k:
                            break
            except Exception as e:
                logger.warning(f"Error searching conversation history: {e}")
        
        return results
    
    def get_conversation_history(
        self,
        conversation_id: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get conversation history for a specific conversation (thread-safe).
        
        Args:
            conversation_id: Unique identifier for the conversation
            limit: Optional limit on number of turns to return
        
        Returns:
            List of conversation turns
        """
        with self._metadata_lock:
            if conversation_id not in self.conversations_metadata:
                return []
            
            turns = self.conversations_metadata[conversation_id].get("turns", [])
            if limit:
                return turns[-limit:].copy()  # Return copy to avoid external modification
            return turns.copy()  # Return copy to avoid external modification
    
    def get_conversation_summary(self, conversation_id: str) -> Optional[str]:
        """Get the summary for a conversation (thread-safe).

        Args:
            conversation_id: Unique identifier for the conversation

        Returns:
            Summary text or None
        """
        with self._metadata_lock:
            if conversation_id not in self.conversations_metadata:
                return None
            return self.conversations_metadata[conversation_id].get("summary")

    # ============================================================================
    # STAGE TRACKING METHODS
    # ============================================================================

    def _initialize_conversation_metadata(self, conversation_id: str):
        """Initialize conversation metadata with default structure including stages."""
        self.conversations_metadata[conversation_id] = {
            "created_at": datetime.now().isoformat(),
            "stage": "NEW",
            "stage_updated_at": datetime.now().isoformat(),
            "stage_history": [
                {"stage": "NEW", "timestamp": datetime.now().isoformat()}
            ],
            "lead_data": {
                "name": None,
                "phone": None,
                "selected_course": None,
                "education_level": None,
                "goal": None,
                "demo_shared": False,
                "enrolled": False
            },
            "turns": [],
            "summary": None
        }

    def update_lead_field(self, conversation_id: str, field: str, value: Any):
        """Update a single lead data field and auto-update stage.

        Args:
            conversation_id: Unique identifier for the conversation
            field: Field name in lead_data (e.g., 'name', 'phone', 'selected_course')
            value: Value to set
        """
        with self._metadata_lock:
            # Initialize if needed
            if conversation_id not in self.conversations_metadata:
                self._initialize_conversation_metadata(conversation_id)
            elif "lead_data" not in self.conversations_metadata[conversation_id]:
                # Migrate old conversations
                self.conversations_metadata[conversation_id]["lead_data"] = {
                    "name": None,
                    "phone": None,
                    "selected_course": None,
                    "education_level": None,
                    "goal": None,
                    "demo_shared": False,
                    "enrolled": False
                }
                self.conversations_metadata[conversation_id]["stage"] = "NEW"
                self.conversations_metadata[conversation_id]["stage_updated_at"] = datetime.now().isoformat()
                self.conversations_metadata[conversation_id]["stage_history"] = [
                    {"stage": "NEW", "timestamp": datetime.now().isoformat()}
                ]

            # Update field
            self.conversations_metadata[conversation_id]["lead_data"][field] = value

            # Auto-detect and update stage
            self._update_stage(conversation_id)

        self._save_metadata()

    def _update_stage(self, conversation_id: str):
        """Auto-detect and update stage based on lead_data (internal method, assumes lock is held)."""
        lead_data = self.conversations_metadata[conversation_id].get("lead_data", {})
        current_stage = self.conversations_metadata[conversation_id].get("stage", "NEW")

        # Detect new stage based on collected data
        if lead_data.get("enrolled"):
            new_stage = "ENROLLED"
        elif lead_data.get("demo_shared"):
            new_stage = "DEMO_SHARED"
        elif lead_data.get("goal"):
            new_stage = "GOAL_COLLECTED"
        elif lead_data.get("education_level"):
            new_stage = "EDUCATION_COLLECTED"
        elif lead_data.get("selected_course"):
            new_stage = "COURSE_SELECTED"
        elif lead_data.get("name"):
            new_stage = "NAME_COLLECTED"
        else:
            new_stage = "NEW"

        # Update if changed
        if new_stage != current_stage:
            self.conversations_metadata[conversation_id]["stage"] = new_stage
            self.conversations_metadata[conversation_id]["stage_updated_at"] = datetime.now().isoformat()

            # Add to history
            if "stage_history" not in self.conversations_metadata[conversation_id]:
                self.conversations_metadata[conversation_id]["stage_history"] = []

            self.conversations_metadata[conversation_id]["stage_history"].append({
                "stage": new_stage,
                "timestamp": datetime.now().isoformat()
            })

    def get_stage(self, conversation_id: str) -> str:
        """Get current stage for a conversation.

        Args:
            conversation_id: Unique identifier for the conversation

        Returns:
            Current stage (e.g., 'NEW', 'COURSE_SELECTED', etc.)
        """
        with self._metadata_lock:
            if conversation_id not in self.conversations_metadata:
                return "NEW"
            return self.conversations_metadata[conversation_id].get("stage", "NEW")

    def get_lead_data(self, conversation_id: str) -> Dict[str, Any]:
        """Get all lead data for a conversation.

        Args:
            conversation_id: Unique identifier for the conversation

        Returns:
            Dictionary with lead data
        """
        with self._metadata_lock:
            if conversation_id not in self.conversations_metadata:
                return {}
            return self.conversations_metadata[conversation_id].get("lead_data", {}).copy()

    def get_leads_by_stage(self, stage: str) -> List[Dict[str, Any]]:
        """Get all leads in a specific stage.

        Args:
            stage: Stage to filter by (e.g., 'COURSE_SELECTED')

        Returns:
            List of leads in that stage with their data
        """
        with self._metadata_lock:
            leads = []
            for conv_id, conv_data in self.conversations_metadata.items():
                if conv_data.get("stage") == stage:
                    leads.append({
                        "conversation_id": conv_id,
                        "stage": conv_data.get("stage"),
                        "stage_updated_at": conv_data.get("stage_updated_at"),
                        "created_at": conv_data.get("created_at"),
                        "lead_data": conv_data.get("lead_data", {})
                    })
            return leads

    def get_all_stage_stats(self) -> Dict[str, Any]:
        """Get statistics for all stages.

        Returns:
            Dictionary with counts for each stage and total leads
        """
        with self._metadata_lock:
            stats = {stage: 0 for stage in self.STAGES.keys()}
            total = 0

            for conv_data in self.conversations_metadata.values():
                stage = conv_data.get("stage", "NEW")
                if stage in stats:
                    stats[stage] += 1
                total += 1

            # Calculate conversion rate
            enrolled = stats.get("ENROLLED", 0)
            conversion_rate = (enrolled / total * 100) if total > 0 else 0

            return {
                "total_leads": total,
                "by_stage": stats,
                "conversion_rate": round(conversion_rate, 2)
            }

    def manually_set_stage(self, conversation_id: str, stage: str):
        """Manually set the stage for a conversation.

        Args:
            conversation_id: Unique identifier for the conversation
            stage: New stage to set
        """
        if stage not in self.STAGES:
            raise ValueError(f"Invalid stage. Must be one of: {list(self.STAGES.keys())}")

        with self._metadata_lock:
            if conversation_id not in self.conversations_metadata:
                self._initialize_conversation_metadata(conversation_id)

            old_stage = self.conversations_metadata[conversation_id].get("stage", "NEW")

            if old_stage != stage:
                self.conversations_metadata[conversation_id]["stage"] = stage
                self.conversations_metadata[conversation_id]["stage_updated_at"] = datetime.now().isoformat()

                # Add to history
                if "stage_history" not in self.conversations_metadata[conversation_id]:
                    self.conversations_metadata[conversation_id]["stage_history"] = []

                self.conversations_metadata[conversation_id]["stage_history"].append({
                    "stage": stage,
                    "timestamp": datetime.now().isoformat(),
                    "manual": True
                })

        self._save_metadata()

