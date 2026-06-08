"""
Feedback & Training System
Collects user feedback and improves agent routing/responses over time.
"""

import sqlite3
import os
import json
from typing import Optional, List, Dict, Tuple
from datetime import datetime


# Database file path
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "feedback.db")


def init_feedback_db():
    """
    Initialize the feedback database with tables for:
    - routing_feedback: Corrections for supervisor routing
    - response_feedback: Quality ratings for agent responses
    - training_examples: Curated examples for each department
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Table 1: Routing Feedback (Supervisor corrections)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS routing_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_query TEXT NOT NULL,
                routed_to TEXT NOT NULL,
                should_route_to TEXT NOT NULL,
                reason TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reviewed_at TIMESTAMP,
                reviewed_by TEXT
            )
        """)
        
        # Table 2: Response Quality Feedback
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS response_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_query TEXT NOT NULL,
                department TEXT NOT NULL,
                response_content TEXT NOT NULL,
                rating INTEGER,
                feedback_text TEXT,
                issue_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Table 3: Training Examples (Curated by admins)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS training_examples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                department TEXT NOT NULL,
                example_query TEXT NOT NULL,
                expected_behavior TEXT NOT NULL,
                notes TEXT,
                active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Table 4: Department Capabilities (What each department should/shouldn't handle)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS department_capabilities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                department TEXT NOT NULL,
                capability_type TEXT NOT NULL,
                description TEXT NOT NULL,
                examples TEXT,
                active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Table 5: Routing Rules (Learned patterns)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS routing_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern TEXT NOT NULL,
                department TEXT NOT NULL,
                confidence REAL DEFAULT 1.0,
                source TEXT DEFAULT 'feedback',
                active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
        print("✅ Feedback database initialized successfully")
    except Exception as e:
        print(f"⚠️  Feedback database initialization error: {e}")


def save_routing_feedback(user_query: str, routed_to: str, should_route_to: str, reason: str = "") -> bool:
    """
    Save feedback about incorrect routing.
    
    Args:
        user_query: The original user query
        routed_to: Department it was routed to (incorrect)
        should_route_to: Department it should have been routed to (correct)
        reason: Optional explanation of why the routing was wrong
        
    Returns:
        True if saved successfully, False otherwise
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO routing_feedback (user_query, routed_to, should_route_to, reason)
            VALUES (?, ?, ?, ?)
        """, (user_query, routed_to, should_route_to, reason))
        
        conn.commit()
        conn.close()
        print(f"✅ Routing feedback saved: '{user_query}' should go to {should_route_to} (was: {routed_to})")
        return True
    except Exception as e:
        print(f"⚠️  Error saving routing feedback: {e}")
        return False


def save_response_feedback(user_query: str, department: str, response_content: str, 
                          rating: int = None, feedback_text: str = "", issue_type: str = "") -> bool:
    """
    Save feedback about response quality.
    
    Args:
        user_query: The original user query
        department: Department that handled the query
        response_content: The response that was generated
        rating: Quality rating (1-5 stars)
        feedback_text: User's feedback comments
        issue_type: Type of issue (e.g., "incorrect_info", "incomplete", "not_helpful")
        
    Returns:
        True if saved successfully, False otherwise
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO response_feedback (user_query, department, response_content, rating, feedback_text, issue_type)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_query, department, response_content, rating, feedback_text, issue_type))
        
        conn.commit()
        conn.close()
        print(f"✅ Response feedback saved for {department} department (rating: {rating})")
        return True
    except Exception as e:
        print(f"⚠️  Error saving response feedback: {e}")
        return False


def add_training_example(department: str, example_query: str, expected_behavior: str, notes: str = "") -> bool:
    """
    Add a training example for a specific department.
    
    Args:
        department: Target department (Engineering, Events, Chat)
        example_query: Example user query
        expected_behavior: What the department should do/return
        notes: Additional context or instructions
        
    Returns:
        True if saved successfully, False otherwise
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO training_examples (department, example_query, expected_behavior, notes)
            VALUES (?, ?, ?, ?)
        """, (department, example_query, expected_behavior, notes))
        
        conn.commit()
        conn.close()
        print(f"✅ Training example added for {department} department")
        return True
    except Exception as e:
        print(f"⚠️  Error adding training example: {e}")
        return False


def add_department_capability(department: str, capability_type: str, description: str, examples: List[str] = None) -> bool:
    """
    Define what a department can/cannot do.
    
    Args:
        department: Target department
        capability_type: "can_handle" or "cannot_handle" or "scope"
        description: Description of the capability/limitation
        examples: List of example queries
        
    Returns:
        True if saved successfully, False otherwise
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        examples_json = json.dumps(examples) if examples else None
        
        cursor.execute("""
            INSERT INTO department_capabilities (department, capability_type, description, examples)
            VALUES (?, ?, ?, ?)
        """, (department, capability_type, description, examples_json))
        
        conn.commit()
        conn.close()
        print(f"✅ Capability defined for {department} department: {capability_type}")
        return True
    except Exception as e:
        print(f"⚠️  Error adding department capability: {e}")
        return False


def get_routing_feedback(status: str = "pending", limit: int = 50) -> List[Dict]:
    """
    Retrieve routing feedback for review.
    
    Args:
        status: Filter by status ("pending", "approved", "rejected")
        limit: Maximum number of records to return
        
    Returns:
        List of feedback records
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, user_query, routed_to, should_route_to, reason, status, created_at
            FROM routing_feedback
            WHERE status = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (status, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        feedback_list = []
        for row in rows:
            feedback_list.append({
                "id": row[0],
                "user_query": row[1],
                "routed_to": row[2],
                "should_route_to": row[3],
                "reason": row[4],
                "status": row[5],
                "created_at": row[6]
            })
        
        return feedback_list
    except Exception as e:
        print(f"⚠️  Error retrieving routing feedback: {e}")
        return []


def get_training_examples(department: str = None, active_only: bool = True) -> List[Dict]:
    """
    Retrieve training examples for a department.
    
    Args:
        department: Filter by department (None = all departments)
        active_only: Only return active examples
        
    Returns:
        List of training examples
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        if department:
            if active_only:
                cursor.execute("""
                    SELECT id, department, example_query, expected_behavior, notes, created_at
                    FROM training_examples
                    WHERE department = ? AND active = 1
                    ORDER BY created_at DESC
                """, (department,))
            else:
                cursor.execute("""
                    SELECT id, department, example_query, expected_behavior, notes, created_at
                    FROM training_examples
                    WHERE department = ?
                    ORDER BY created_at DESC
                """, (department,))
        else:
            if active_only:
                cursor.execute("""
                    SELECT id, department, example_query, expected_behavior, notes, created_at
                    FROM training_examples
                    WHERE active = 1
                    ORDER BY department, created_at DESC
                """)
            else:
                cursor.execute("""
                    SELECT id, department, example_query, expected_behavior, notes, created_at
                    FROM training_examples
                    ORDER BY department, created_at DESC
                """)
        
        rows = cursor.fetchall()
        conn.close()
        
        examples = []
        for row in rows:
            examples.append({
                "id": row[0],
                "department": row[1],
                "example_query": row[2],
                "expected_behavior": row[3],
                "notes": row[4],
                "created_at": row[5]
            })
        
        return examples
    except Exception as e:
        print(f"⚠️  Error retrieving training examples: {e}")
        return []


def get_department_capabilities(department: str = None) -> List[Dict]:
    """
    Retrieve department capabilities and limitations.
    
    Args:
        department: Filter by department (None = all departments)
        
    Returns:
        List of capability definitions
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        if department:
            cursor.execute("""
                SELECT id, department, capability_type, description, examples, active
                FROM department_capabilities
                WHERE department = ? AND active = 1
                ORDER BY capability_type
            """, (department,))
        else:
            cursor.execute("""
                SELECT id, department, capability_type, description, examples, active
                FROM department_capabilities
                WHERE active = 1
                ORDER BY department, capability_type
            """)
        
        rows = cursor.fetchall()
        conn.close()
        
        capabilities = []
        for row in rows:
            examples = json.loads(row[4]) if row[4] else []
            capabilities.append({
                "id": row[0],
                "department": row[1],
                "capability_type": row[2],
                "description": row[3],
                "examples": examples,
                "active": row[5]
            })
        
        return capabilities
    except Exception as e:
        print(f"⚠️  Error retrieving department capabilities: {e}")
        return []


def approve_routing_feedback(feedback_id: int, reviewer: str = "admin") -> bool:
    """
    Approve routing feedback and potentially create a routing rule.
    
    Args:
        feedback_id: ID of the feedback record
        reviewer: Name/ID of the reviewer
        
    Returns:
        True if approved successfully, False otherwise
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Get the feedback record
        cursor.execute("""
            SELECT user_query, should_route_to FROM routing_feedback WHERE id = ?
        """, (feedback_id,))
        
        result = cursor.fetchone()
        if not result:
            print(f"⚠️  Feedback ID {feedback_id} not found")
            conn.close()
            return False
        
        user_query, should_route_to = result
        
        # Update feedback status
        cursor.execute("""
            UPDATE routing_feedback
            SET status = 'approved', reviewed_at = ?, reviewed_by = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), reviewer, feedback_id))
        
        # Extract key patterns from the query (simple keyword extraction)
        # This could be enhanced with NLP/ML in the future
        keywords = [word.lower() for word in user_query.split() if len(word) > 3]
        
        # Create routing rule for common patterns
        if keywords:
            pattern = " ".join(keywords[:3])  # Use first 3 significant words
            cursor.execute("""
                INSERT INTO routing_rules (pattern, department, confidence, source)
                VALUES (?, ?, ?, ?)
            """, (pattern, should_route_to, 0.8, f"feedback_{feedback_id}"))
        
        conn.commit()
        conn.close()
        print(f"✅ Routing feedback approved and rule created")
        return True
    except Exception as e:
        print(f"⚠️  Error approving routing feedback: {e}")
        return False


def get_response_feedback_summary(department: str = None, min_rating: int = None) -> Dict:
    """
    Get summary statistics of response feedback.
    
    Args:
        department: Filter by department (None = all)
        min_rating: Filter by minimum rating
        
    Returns:
        Dictionary with summary statistics
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Build query based on filters
        where_clauses = []
        params = []
        
        if department:
            where_clauses.append("department = ?")
            params.append(department)
        
        if min_rating:
            where_clauses.append("rating >= ?")
            params.append(min_rating)
        
        where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        
        # Get average rating
        cursor.execute(f"""
            SELECT AVG(rating), COUNT(*), department
            FROM response_feedback
            {where_sql}
            GROUP BY department
        """, params)
        
        rows = cursor.fetchall()
        conn.close()
        
        summary = {}
        for row in rows:
            dept = row[2]
            summary[dept] = {
                "average_rating": round(row[0], 2) if row[0] else None,
                "total_feedback": row[1]
            }
        
        return summary
    except Exception as e:
        print(f"⚠️  Error getting feedback summary: {e}")
        return {}


def get_common_issues(department: str = None, limit: int = 10) -> List[Tuple[str, int]]:
    """
    Get most common issue types reported.
    
    Args:
        department: Filter by department
        limit: Maximum number of issues to return
        
    Returns:
        List of (issue_type, count) tuples
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        if department:
            cursor.execute("""
                SELECT issue_type, COUNT(*) as count
                FROM response_feedback
                WHERE department = ? AND issue_type IS NOT NULL
                GROUP BY issue_type
                ORDER BY count DESC
                LIMIT ?
            """, (department, limit))
        else:
            cursor.execute("""
                SELECT issue_type, COUNT(*) as count
                FROM response_feedback
                WHERE issue_type IS NOT NULL
                GROUP BY issue_type
                ORDER BY count DESC
                LIMIT ?
            """, (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [(row[0], row[1]) for row in rows]
    except Exception as e:
        print(f"⚠️  Error getting common issues: {e}")
        return []


# Initialize database on module import
init_feedback_db()
