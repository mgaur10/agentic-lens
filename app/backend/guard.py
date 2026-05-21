"""
Security Guard Layer - Zero Trust Input Validation
Filters potentially malicious inputs before they reach agents.
"""

import re
from typing import Tuple


class SecurityGuard:
    """
    Security layer that validates user inputs using pattern matching.
    Implements Zero Trust security model.
    """
    
    # Blocked patterns (case-insensitive)
    BLOCKED_PATTERNS = [
        r'\bhack\b',
        r'\bignore\b',
        r'\bbypass\b'
    ]
    
    def __init__(self):
        """Initialize the Security Guard."""
        # Compile patterns for efficiency
        self.compiled_patterns = [
            re.compile(pattern, re.IGNORECASE) 
            for pattern in self.BLOCKED_PATTERNS
        ]
    
    def validate(self, input_text: str) -> Tuple[bool, str]:
        """
        Validate input text for security threats.
        
        Args:
            input_text: The user input to validate
            
        Returns:
            Tuple of (is_safe: bool, message: str)
            - (True, "Input Safe") if input passes validation
            - (False, "SECURITY ALERT: Injection Attempt Detected") if threat detected
        """
        if not input_text or not isinstance(input_text, str):
            return (False, "SECURITY ALERT: Invalid input type")
        
        # Check against blocked patterns
        for pattern in self.compiled_patterns:
            if pattern.search(input_text):
                # Security alert logged via return message (no print statements in production)
                return (False, "SECURITY ALERT: Injection Attempt Detected")
        
        return (True, "Input Safe")
