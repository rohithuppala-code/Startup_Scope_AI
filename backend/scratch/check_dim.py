from google import genai
import sys
sys.path.append(".")
from app.core.config import settings

client = genai.Client(api_key=settings.GEMINI_API_KEY)

text = "This is a test startup idea description."
model = "gemini-embedding-001"

print(f"Generating embedding using {model}...")
try:
    response = client.models.embed_content(
        model=model,
        contents=text,
    )
    if hasattr(response, "embedding") and response.embedding:
        values = response.embedding.values
        print(f"Dimension: {len(values)}")
    elif hasattr(response, "embeddings") and response.embeddings:
        values = response.embeddings[0].values
        print(f"Dimension: {len(values)}")
    else:
        print("No embedding found in response.")
except Exception as e:
    print(f"Error: {e}")
