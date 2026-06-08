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
        """
        for pattern in self.compiled_patterns:
            if pattern.search(input_text):
                return (False, f"Blocked by Zero Trust Policy: Detected malicious keyword pattern.")
        return (True, "Input Safe")
