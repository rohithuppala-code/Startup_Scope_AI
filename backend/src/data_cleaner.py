import re

def clean_markdown(raw_md: str) -> str:
    """
    Cleans raw markdown by removing excessive whitespaces and 
    truncating overly long sections to fit context bounds.
    """
    # Remove multiple newlines
    cleaned = re.sub(r'\n{3,}', '\n\n', raw_md)
    # Remove excessive whitespace
    cleaned = re.sub(r' {3,}', ' ', cleaned)
    
    return cleaned

def limit_context(text: str, max_chars: int = 15000) -> str:
    """
    Limits context string to a maximum number of characters to 
    fit within conservative LLM prompt limits.
    """
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...[Content truncated due to size limits]..."
