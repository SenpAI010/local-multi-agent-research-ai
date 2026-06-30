"""
SemanticStore: Vector database integration using Chroma for RAG.
Stores and retrieves knowledge with semantic similarity search.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import uuid
import re

try:
    import chromadb
except ImportError:
    chromadb = None


class SemanticStore:
    """Vector database for semantic knowledge storage and retrieval."""
    
    def __init__(self, db_path: Path):
        """
        Initialize Chroma vector database.
        
        Args:
            db_path: Path to chroma database directory
        """
        self.db_path = Path(db_path)
        self.db_path.mkdir(parents=True, exist_ok=True)
        self.fallback_file = self.db_path / "knowledge_fallback.json"
        self.use_fallback = chromadb is None

        if self.use_fallback:
            self.collection = None
            return
        
        # Initialize Chroma client (v0.4+ uses PersistentClient)
        try:
            self.client = chromadb.PersistentClient(path=str(self.db_path))
        except AttributeError:
            self.use_fallback = True
            self.collection = None
            return
        
        # Get or create collection for knowledge
        self.collection = self.client.get_or_create_collection(
            name="knowledge_base",
            metadata={"description": "Semantic knowledge base for RAG"}
        )

    def _load_fallback(self) -> List[Dict[str, Any]]:
        if not self.fallback_file.exists():
            return []
        try:
            return json.loads(self.fallback_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []

    def _save_fallback(self, items: List[Dict[str, Any]]) -> None:
        self.fallback_file.write_text(
            json.dumps(items, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _token_relevance(self, query: str, text: str) -> float:
        query_tokens = set(re.findall(r"\w+", query.lower()))
        text_tokens = set(re.findall(r"\w+", text.lower()))
        if not query_tokens or not text_tokens:
            return 0.0
        overlap = len(query_tokens & text_tokens)
        return overlap / max(len(query_tokens), 1)
    
    def add_knowledge(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        doc_id: Optional[str] = None
    ) -> str:
        """
        Add knowledge to vector database.
        
        Args:
            text: Knowledge text to store
            metadata: Optional metadata dict
            doc_id: Optional custom ID (auto-generated if None)
            
        Returns:
            Document ID
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")
        
        doc_id = doc_id or str(uuid.uuid4())
        
        metadata = metadata or {}
        metadata.update({
            "timestamp": datetime.now().isoformat(),
            "type": metadata.get("type", "general")
        })

        if self.use_fallback:
            items = self._load_fallback()
            items.append({"id": doc_id, "text": text, "metadata": metadata})
            self._save_fallback(items)
            return doc_id
        
        self.collection.add(
            ids=[doc_id],
            documents=[text],
            metadatas=[metadata]
        )
        
        return doc_id
    
    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        min_distance: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Retrieve semantically similar documents.
        
        Args:
            query: Query text
            top_k: Number of results
            min_distance: Minimum relevance score (0-1)
            
        Returns:
            List of {id, text, metadata, distance} dicts
        """
        if not query or not query.strip():
            return []

        if self.use_fallback:
            items = self._load_fallback()
            scored = []
            for item in items:
                relevance = self._token_relevance(query, item.get("text", ""))
                if relevance >= min_distance:
                    scored.append({**item, "relevance": relevance})
            scored.sort(key=lambda item: item["relevance"], reverse=True)
            return scored[:top_k]
        
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k,
            include=["documents", "metadatas", "distances"]
        )
        
        if not results or not results['ids'] or not results['ids'][0]:
            return []
        
        # Format results
        retrieved = []
        for i, doc_id in enumerate(results['ids'][0]):
            distance = results['distances'][0][i] if results['distances'] else 0
            
            # Chroma uses L2 distance (lower = better)
            relevance = 1 / (1 + distance)
            
            if relevance >= min_distance:
                retrieved.append({
                    'id': doc_id,
                    'text': results['documents'][0][i],
                    'metadata': results['metadatas'][0][i],
                    'relevance': relevance
                })
        
        return retrieved
    
    def update_knowledge(self, doc_id: str, text: str, metadata: Optional[Dict] = None):
        """Update existing knowledge document."""
        metadata = metadata or {}
        metadata.update({"updated": datetime.now().isoformat()})

        if self.use_fallback:
            items = self._load_fallback()
            for item in items:
                if item["id"] == doc_id:
                    item["text"] = text
                    item["metadata"] = metadata
                    break
            self._save_fallback(items)
            return
        
        self.collection.update(
            ids=[doc_id],
            documents=[text],
            metadatas=[metadata]
        )
    
    def delete_knowledge(self, doc_id: str):
        """Delete knowledge document by ID."""
        if self.use_fallback:
            items = [item for item in self._load_fallback() if item["id"] != doc_id]
            self._save_fallback(items)
            return

        self.collection.delete(ids=[doc_id])
    
    def get_knowledge(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve specific knowledge document."""
        if self.use_fallback:
            for item in self._load_fallback():
                if item["id"] == doc_id:
                    return item
            return None

        results = self.collection.get(
            ids=[doc_id],
            include=["documents", "metadatas"]
        )
        
        if not results or not results['ids']:
            return None
        
        return {
            'id': doc_id,
            'text': results['documents'][0],
            'metadata': results['metadatas'][0]
        }
    
    def list_knowledge(self, limit: int = 100) -> List[Dict[str, Any]]:
        """List all stored knowledge."""
        if self.use_fallback:
            return self._load_fallback()[:limit]

        results = self.collection.get(
            limit=limit,
            include=["documents", "metadatas"]
        )
        
        if not results or not results['ids']:
            return []
        
        knowledge = []
        for i, doc_id in enumerate(results['ids']):
            knowledge.append({
                'id': doc_id,
                'text': results['documents'][i],
                'metadata': results['metadatas'][i]
            })
        
        return knowledge
    
    def clear_all(self):
        """Clear all knowledge (use with caution!)."""
        if self.use_fallback:
            self._save_fallback([])
            return

        # Get all IDs and delete them
        results = self.collection.get(include=[])
        if results and results['ids']:
            self.collection.delete(ids=results['ids'])
    
    def get_count(self) -> int:
        """Get total number of documents."""
        if self.use_fallback:
            return len(self._load_fallback())

        results = self.collection.get(include=[])
        return len(results.get('ids', []))
    
    def export_knowledge(self, filepath: Path):
        """Export all knowledge to JSON."""
        knowledge = self.list_knowledge(limit=10000)
        
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(knowledge, f, indent=2, ensure_ascii=False)
    
    def import_knowledge(self, filepath: Path, skip_duplicates: bool = True):
        """Import knowledge from JSON."""
        with open(filepath, 'r', encoding='utf-8') as f:
            knowledge = json.load(f)
        
        count = 0
        for item in knowledge:
            if skip_duplicates and self.get_knowledge(item['id']):
                continue
            
            self.add_knowledge(
                text=item['text'],
                metadata=item.get('metadata', {}),
                doc_id=item['id']
            )
            count += 1
        
        return count
