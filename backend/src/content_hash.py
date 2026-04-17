"""Content hash computation utilities for change detection."""
import hashlib
import re


def compute_content_hash(content: str) -> str:
    """
    Compute normalized content hash for change detection.
    
    Removes timestamps, dynamic content, and whitespace variations to ensure
    that only meaningful content changes trigger alerts.
    
    Args:
        content: Raw content string to hash
        
    Returns:
        SHA-256 hash of normalized content as hexadecimal string
        
    Example:
        >>> compute_content_hash("Hello World  2024-01-15")
        'a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e'
    """
    if not content:
        return hashlib.sha256(b'').hexdigest()
    
    # Remove common dynamic elements
    normalized = content
    
    # Remove dates in various formats (YYYY-MM-DD, MM/DD/YYYY, etc.)
    normalized = re.sub(r'\d{4}-\d{2}-\d{2}', '', normalized)
    normalized = re.sub(r'\d{1,2}/\d{1,2}/\d{2,4}', '', normalized)
    
    # Remove times (HH:MM:SS, HH:MM)
    normalized = re.sub(r'\d{1,2}:\d{2}(:\d{2})?', '', normalized)
    
    # Remove timestamps (Unix epoch, ISO 8601)
    normalized = re.sub(r'\d{10,13}', '', normalized)
    
    # Normalize whitespace (multiple spaces, tabs, newlines to single space)
    normalized = re.sub(r'\s+', ' ', normalized)
    
    # Convert to lowercase for case-insensitive comparison
    normalized = normalized.lower().strip()
    
    # Compute SHA-256 hash
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def content_changed(old_hash: str, new_hash: str) -> bool:
    """
    Check if content has changed based on hash comparison.
    
    Args:
        old_hash: Previous content hash
        new_hash: Current content hash
        
    Returns:
        True if content has changed, False otherwise
    """
    return old_hash != new_hash
