import os
from google import genai
import sys
sys.path.append(".")
from app.core.config import settings

client = genai.Client(api_key=settings.GEMINI_API_KEY)

print("Listing all models...")
try:
    for model in client.models.list():
        print(f" - {model.name}")
except Exception as e:
    print(f"Error: {e}")
