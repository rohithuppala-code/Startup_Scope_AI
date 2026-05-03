import json
from typing import Any

import traceback

def clean_error(e: Exception) -> str:
    """
    Extracts a clean, human-readable message from huge API error traces.
    Useful for keeping terminal logs readable when providers return massive JSON error payloads.
    
    WARNING: For rigorous debugging, this now ALWAYS prints the full traceback 
    to the terminal before returning the cleaned string to the caller.
    """
    print("\n" + "="*60, flush=True)
    print(f"🔥 RIGOROUS ERROR LOG DUMP 🔥", flush=True)
    print(f"Exception Type: {type(e).__name__}", flush=True)
    print(f"Traceback:\n{traceback.format_exc()}", flush=True)
    print("="*60 + "\n", flush=True)

    try:
        from google.genai.errors import APIError
        if isinstance(e, APIError):
            return f"APIError {e.code}: {e.message}"
    except ImportError:
        pass

    e_str = str(e)
    
    # Catch raw 429 JSON payloads that stringify aggressively
    if "429" in e_str or "RESOURCE_EXHAUSTED" in e_str or "quota" in e_str.lower():
        return "429 RESOURCE_EXHAUSTED (Rate Limit or Quota Exceeded)"
    
    if "503" in e_str:
        return "503 Service Unavailable"
        
    # Return first line or truncate to avoid massive wall of text
    first_line = e_str.split('\n')[0]
    return first_line[:250] + ("..." if len(first_line) > 250 else "")
