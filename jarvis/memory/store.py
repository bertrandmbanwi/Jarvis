"""
JARVIS Memory Store (v2: Phase 6.3 Persistent Memory)

Persistent vector-based memory using ChromaDB, enriched with:
- Fact extraction: structured knowledge about the user
- Preference tracking: implicit behavior patterns
- Categorized retrieval: different memory types for different contexts

Gives JARVIS the ability to remember conversations, learn user facts,
and adapt to preferences over time.
"""
import logging
import time
from typing import Optional

from jarvis.memory.facts import FactStore
from jarvis.memory.preferences import PreferenceTracker

logger = logging.getLogger("jarvis.memory")

try:
    import chromadb
    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False
    logger.warning("ChromaDB not installed. Using in-memory storage only.")


class MemoryStore:
    """Long-term memory combining vector store, facts, and preferences."""

    def __init__(self):
        self._client = None
        self._collection = None
        self._fallback_memory: list[dict] = []
        self._counter = 0
        self.facts = FactStore()
        self.preferences = PreferenceTracker()

    def initialize(self):
        """Initialize all memory systems."""
        self.facts.load()
        self.preferences.load()
        if HAS_CHROMA:
            try:
                from jarvis.config import settings
                self._client = chromadb.PersistentClient(
                    path=settings.CHROMA_PERSIST_DIR,
                )
                self._collection = self._client.get_or_create_collection(
                    name=settings.MEMORY_COLLECTION,
                    metadata={"description": "JARVIS conversation memory"},
                )
                count = self._collection.count()
                logger.info(
                    "ChromaDB initialized (persistent). %d memories stored.", count
                )
            except Exception as e:
                logger.warning("ChromaDB persistent init failed (%s). Trying in-memory.", e)
                self._try_simple_chroma()
        else:
            logger.info("Using in-memory fallback for memory storage.")

    def _try_simple_chroma(self):
        """Try a simpler ChromaDB initialization."""
        try:
            self._client = chromadb.Client()
            self._collection = self._client.get_or_create_collection(
                name="jarvis_conversations"
            )
            logger.info("ChromaDB initialized (in-memory mode).")
        except Exception as e:
            logger.warning("ChromaDB fallback also failed: %s", e)
            self._client = None
            self._collection = None

    def add(self, text: str, metadata: Optional[dict] = None):
        """Add a memory entry."""
        self._counter += 1
        doc_id = f"mem_{self._counter}_{int(time.time())}"

        if self._collection is not None:
            try:
                self._collection.add(
                    documents=[text],
                    ids=[doc_id],
                    metadatas=[metadata or {}],
                )
                return
            except Exception as e:
                logger.warning("ChromaDB add failed: %s", e)

        self._fallback_memory.append({
            "id": doc_id,
            "text": text,
            "metadata": metadata or {},
        })
        if len(self._fallback_memory) > 1000:
            self._fallback_memory = self._fallback_memory[-500:]

    def search(self, query: str, top_k: int = 5) -> list[str]:
        """Search memories by semantic similarity."""
        if self._collection is not None:
            try:
                results = self._collection.query(
                    query_texts=[query],
                    n_results=min(top_k, max(self._collection.count(), 1)),
                )
                documents = results.get("documents", [[]])[0]
                return documents
            except Exception as e:
                logger.warning("ChromaDB search failed: %s", e)

        recent = self._fallback_memory[-top_k:]
        return [m["text"] for m in recent]

    def get_enriched_context(self, query: str, top_k: int = 3) -> str:
        """Get enriched context combining facts, preferences, and memories."""
        parts = []

        facts_context = self.facts.get_context_string(max_facts=15)
        if facts_context:
            parts.append(facts_context)

        prefs_context = self.preferences.get_context_string()
        if prefs_context:
            parts.append(prefs_context)

        memories = self.search(query, top_k=top_k)
        if memories:
            memory_lines = [f"[Past context: {m}]" for m in memories]
            parts.append("\n".join(memory_lines))

        return "\n\n".join(parts)

    def process_exchange(self, user_message: str, assistant_response: str, tier: str = "", tool_calls: list[str] = None):
        """Process an exchange for fact extraction and preference learning."""
        try:
            new_facts = self.facts.extract_from_exchange(user_message, assistant_response)
            if new_facts:
                logger.info(
                    "Extracted %d new fact(s): %s",
                    len(new_facts),
                    [(f.subject, f.value) for f in new_facts],
                )
        except Exception as e:
            logger.debug("Fact extraction failed (non-critical): %s", e)

        try:
            self.preferences.record_request(user_message, tier, tool_calls)
        except Exception as e:
            logger.debug("Preference recording failed (non-critical): %s", e)

    def save_all(self):
        """Save all memory systems to disk."""
        self.facts.save()
        self.preferences.save()
        logger.debug("All memory systems saved.")

    def consolidate(self):
        """Run maintenance on all memory systems."""
        self.facts.consolidate()
        self.facts.save()
        self.preferences.save()

    def get_stats(self) -> dict:
        """Get comprehensive memory statistics."""
        vector_stats = {}
        if self._collection is not None:
            try:
                vector_stats = {
                    "backend": "chromadb",
                    "count": self._collection.count(),
                }
            except Exception:
                vector_stats = {"backend": "chromadb", "count": "error"}
        else:
            vector_stats = {
                "backend": "in-memory",
                "count": len(self._fallback_memory),
            }

        return {
            "vector_store": vector_stats,
            "facts": self.facts.get_stats(),
            "preferences": self.preferences.get_stats(),
        }
