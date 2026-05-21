"""
Supervisor Training Module
Uses feedback data to improve routing decisions over time.
"""

from typing import List, Dict, Tuple
from backend import feedback
import re


class SupervisorTrainer:
    """
    Trains the Supervisor agent using feedback data.
    Generates routing suggestions based on learned patterns.
    """
    
    def __init__(self):
        """Initialize the trainer."""
        self.learned_patterns = self._load_learned_patterns()
        self.department_capabilities = self._load_capabilities()
    
    def _load_learned_patterns(self) -> Dict[str, List[str]]:
        """
        Load learned routing patterns from approved feedback.
        
        Returns:
            Dictionary mapping departments to lists of pattern keywords
        """
        patterns = {
            "Engineering": [],
            "Events": [],
            "X-Ray": [],
            "Chat": []
        }
        
        # Get approved routing feedback
        approved_feedback = feedback.get_routing_feedback(status="approved", limit=1000)
        
        for item in approved_feedback:
            dept = item["should_route_to"]
            query = item["user_query"].lower()
            
            # Extract significant keywords (words > 3 chars)
            keywords = [word for word in query.split() if len(word) > 3 and word.isalpha()]
            
            if dept in patterns:
                patterns[dept].extend(keywords)
        
        # Remove duplicates and sort by frequency
        for dept in patterns:
            # Count frequency
            word_freq = {}
            for word in patterns[dept]:
                word_freq[word] = word_freq.get(word, 0) + 1
            
            # Keep words that appear more than once (significant patterns)
            patterns[dept] = [word for word, freq in word_freq.items() if freq > 1]
        
        return patterns
    
    def _load_capabilities(self) -> Dict[str, Dict]:
        """
        Load department capabilities from the database.
        
        Returns:
            Dictionary mapping departments to their capabilities
        """
        capabilities = {
            "Engineering": {"can_handle": [], "cannot_handle": [], "scope": []},
            "Events": {"can_handle": [], "cannot_handle": [], "scope": []},
            "X-Ray": {"can_handle": [], "cannot_handle": [], "scope": []},
            "Chat": {"can_handle": [], "cannot_handle": [], "scope": []}
        }
        
        all_caps = feedback.get_department_capabilities()
        
        for cap in all_caps:
            dept = cap["department"]
            cap_type = cap["capability_type"]
            
            if dept in capabilities and cap_type in capabilities[dept]:
                capabilities[dept][cap_type].append({
                    "description": cap["description"],
                    "examples": cap["examples"]
                })
        
        return capabilities
    
    def suggest_routing(self, user_query: str) -> Tuple[str, float, str]:
        """
        Suggest routing based on learned patterns.
        
        Args:
            user_query: The user's query
            
        Returns:
            Tuple of (suggested_department, confidence, reason)
        """
        query_lower = user_query.lower()
        scores = {
            "Engineering": 0,
            "Events": 0,
            "X-Ray": 0,
            "Chat": 0
        }
        
        # Score based on learned patterns
        for dept, keywords in self.learned_patterns.items():
            for keyword in keywords:
                if keyword in query_lower:
                    scores[dept] += 1
        
        # Check against capability definitions
        for dept, caps in self.department_capabilities.items():
            # Check "can_handle" examples
            for cap in caps["can_handle"]:
                for example in cap["examples"]:
                    if example.lower() in query_lower:
                        scores[dept] += 2  # Higher weight for explicit examples
            
            # Check "cannot_handle" examples (negative score)
            for cap in caps["cannot_handle"]:
                for example in cap["examples"]:
                    if example.lower() in query_lower:
                        scores[dept] -= 3  # Strong negative signal
        
        # Find best match
        if max(scores.values()) == 0:
            return ("Chat", 0.0, "No learned patterns match")
        
        best_dept = max(scores, key=scores.get)
        total_score = sum(abs(s) for s in scores.values())
        confidence = scores[best_dept] / total_score if total_score > 0 else 0.0
        
        reason = f"Matched {scores[best_dept]} learned patterns"
        
        return (best_dept, confidence, reason)
    
    def get_training_prompt_additions(self, department: str) -> str:
        """
        Generate additional prompt text based on training examples.
        
        Args:
            department: Target department
            
        Returns:
            Formatted prompt text with examples
        """
        examples = feedback.get_training_examples(department=department, active_only=True)
        
        if not examples:
            return ""
        
        prompt_text = f"\n\n**Training Examples for {department}:**\n"
        
        for idx, example in enumerate(examples[:5], 1):  # Limit to 5 examples
            prompt_text += f"{idx}. Query: \"{example['example_query']}\"\n"
            prompt_text += f"   Expected: {example['expected_behavior']}\n"
            if example['notes']:
                prompt_text += f"   Note: {example['notes']}\n"
        
        return prompt_text
    
    def get_capability_prompt_additions(self, department: str) -> str:
        """
        Generate prompt text describing department capabilities.
        
        Args:
            department: Target department
            
        Returns:
            Formatted prompt text with capabilities
        """
        if department not in self.department_capabilities:
            return ""
        
        caps = self.department_capabilities[department]
        prompt_text = f"\n\n**{department} Department Scope:**\n"
        
        # Can handle
        if caps["can_handle"]:
            prompt_text += "\n✅ **Can Handle:**\n"
            for cap in caps["can_handle"]:
                prompt_text += f"- {cap['description']}\n"
                if cap['examples']:
                    prompt_text += f"  Examples: {', '.join(cap['examples'][:3])}\n"
        
        # Cannot handle
        if caps["cannot_handle"]:
            prompt_text += "\n❌ **Cannot Handle:**\n"
            for cap in caps["cannot_handle"]:
                prompt_text += f"- {cap['description']}\n"
                if cap['examples']:
                    prompt_text += f"  Examples: {', '.join(cap['examples'][:3])}\n"
        
        # Scope
        if caps["scope"]:
            prompt_text += "\n🎯 **Scope:**\n"
            for cap in caps["scope"]:
                prompt_text += f"- {cap['description']}\n"
        
        return prompt_text
    
    def get_routing_feedback_summary(self) -> Dict[str, int]:
        """
        Get summary of routing corrections.
        
        Returns:
            Dictionary with correction counts
        """
        approved = feedback.get_routing_feedback(status="approved", limit=1000)
        
        corrections = {}
        for item in approved:
            key = f"{item['routed_to']} → {item['should_route_to']}"
            corrections[key] = corrections.get(key, 0) + 1
        
        return corrections
    
    def generate_routing_report(self) -> str:
        """
        Generate a human-readable report of learned patterns.
        
        Returns:
            Formatted report string
        """
        report = "# Supervisor Training Report\n\n"
        
        # Learned patterns
        report += "## Learned Patterns\n\n"
        for dept, keywords in self.learned_patterns.items():
            if keywords:
                report += f"### {dept} Department\n"
                report += f"Keywords: {', '.join(keywords[:10])}\n\n"
        
        # Routing corrections
        report += "## Routing Corrections Applied\n\n"
        corrections = self.get_routing_feedback_summary()
        for correction, count in sorted(corrections.items(), key=lambda x: x[1], reverse=True):
            report += f"- {correction}: {count} times\n"
        
        # Training examples count
        report += "\n## Training Examples\n\n"
        for dept in ["Engineering", "Events", "Chat"]:
            examples = feedback.get_training_examples(department=dept, active_only=True)
            report += f"- {dept}: {len(examples)} examples\n"
        
        return report
    
    def should_override_routing(self, user_query: str, supervisor_choice: str) -> Tuple[bool, str, str]:
        """
        Check if the supervisor's routing should be overridden based on learned patterns.
        
        Args:
            user_query: The user's query
            supervisor_choice: Department chosen by supervisor
            
        Returns:
            Tuple of (should_override, suggested_dept, reason)
        """
        suggested_dept, confidence, reason = self.suggest_routing(user_query)
        
        # Only override if confidence is high and different from supervisor's choice
        if confidence > 0.7 and suggested_dept != supervisor_choice:
            return (True, suggested_dept, f"High confidence ({confidence:.0%}) based on learned patterns: {reason}")
        
        return (False, supervisor_choice, "")
    
    def get_scope_violations(self, user_query: str, department: str) -> List[str]:
        """
        Check if a query violates department scope.
        
        Args:
            user_query: The user's query
            department: Department to check
            
        Returns:
            List of violation messages
        """
        violations = []
        
        if department not in self.department_capabilities:
            return violations
        
        caps = self.department_capabilities[department]
        query_lower = user_query.lower()
        
        # Check "cannot_handle" examples
        for cap in caps["cannot_handle"]:
            for example in cap["examples"]:
                if example.lower() in query_lower:
                    violations.append(f"⚠️ {department} cannot handle: {cap['description']}")
        
        return violations
