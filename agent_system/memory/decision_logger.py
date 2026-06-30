"""
DecisionLogger: Tracks important decisions and their reasoning.
Integrates with SQLite memory for persistent decision history.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional


class DecisionLogger:
    """Logs and retrieves decision history with reasoning."""
    
    def __init__(self, db_path: Path):
        """
        Initialize decision logger with SQLite backend.
        
        Args:
            db_path: Path to SQLite database
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._init_db()
    
    def _init_db(self):
        """Initialize decision tracking table if not exists."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                title TEXT NOT NULL,
                decision TEXT NOT NULL,
                reasoning TEXT NOT NULL,
                context TEXT,
                outcome TEXT,
                tags TEXT,
                confidence REAL
            )
            """)
            conn.commit()
    
    def log_decision(
        self,
        title: str,
        decision: str,
        reasoning: str,
        context: Optional[str] = None,
        tags: Optional[List[str]] = None,
        confidence: float = 1.0
    ) -> int:
        """
        Log a decision with reasoning.
        
        Args:
            title: Brief decision title
            decision: What decision was made
            reasoning: Why that decision was made
            context: Optional context (code snippet, error, etc.)
            tags: Optional tags for categorization
            confidence: Confidence level (0-1)
            
        Returns:
            Decision ID
        """
        tags = tags or []
        timestamp = datetime.now().isoformat()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO decisions
                (timestamp, title, decision, reasoning, context, tags, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    title,
                    decision,
                    reasoning,
                    context,
                    json.dumps(tags),
                    confidence
                )
            )
            conn.commit()
            return cursor.lastrowid
    
    def get_decision(self, decision_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve specific decision by ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM decisions WHERE id = ?",
                (decision_id,)
            )
            row = cursor.fetchone()
            
            if not row:
                return None
            
            return self._row_to_dict(row)
    
    def get_decision_history(
        self,
        limit: int = 50,
        tags: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get recent decision history.
        
        Args:
            limit: Max number of decisions
            tags: Optional tag filter
            
        Returns:
            List of decision dicts
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            if tags:
                # Filter by tags (any match)
                query = "SELECT * FROM decisions WHERE "
                conditions = []
                params = []
                
                for tag in tags:
                    conditions.append("tags LIKE ?")
                    params.append(f'%"{tag}"%')
                
                query += " OR ".join(conditions)
                query += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit)
                
                cursor = conn.execute(query, params)
            else:
                cursor = conn.execute(
                    "SELECT * FROM decisions ORDER BY timestamp DESC LIMIT ?",
                    (limit,)
                )
            
            return [self._row_to_dict(row) for row in cursor.fetchall()]
    
    def find_similar_decisions(
        self,
        topic: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find decisions related to a topic (search in title/reasoning).
        
        Args:
            topic: Search topic
            limit: Max results
            
        Returns:
            List of relevant decisions
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            search_term = f"%{topic}%"
            cursor = conn.execute(
                """
                SELECT * FROM decisions
                WHERE title LIKE ? OR decision LIKE ? OR reasoning LIKE ?
                ORDER BY timestamp DESC LIMIT ?
                """,
                (search_term, search_term, search_term, limit)
            )
            
            return [self._row_to_dict(row) for row in cursor.fetchall()]
    
    def update_outcome(self, decision_id: int, outcome: str):
        """Update decision with actual outcome."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE decisions SET outcome = ? WHERE id = ?",
                (outcome, decision_id)
            )
            conn.commit()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get decision statistics."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM decisions")
            total = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT AVG(confidence) FROM decisions")
            avg_conf = cursor.fetchone()[0] or 0.0
            
            cursor = conn.execute(
                "SELECT COUNT(*) FROM decisions WHERE outcome IS NOT NULL"
            )
            outcomes = cursor.fetchone()[0]
            
            return {
                'total_decisions': total,
                'avg_confidence': round(avg_conf, 2),
                'decisions_with_outcome': outcomes,
                'pending_decisions': total - outcomes
            }
    
    def export_decisions(self, filepath: Path):
        """Export all decisions to JSON."""
        decisions = self.get_decision_history(limit=10000)
        
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(decisions, f, indent=2, ensure_ascii=False)
    
    def close(self):
        """Close database connection (no-op, but for compatibility)."""
        pass
    
    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        """Convert SQLite row to dict."""
        return {
            'id': row['id'],
            'timestamp': row['timestamp'],
            'title': row['title'],
            'decision': row['decision'],
            'reasoning': row['reasoning'],
            'context': row['context'],
            'outcome': row['outcome'],
            'tags': json.loads(row['tags']) if row['tags'] else [],
            'confidence': row['confidence']
        }
