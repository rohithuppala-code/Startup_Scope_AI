from google import genai
import sys
sys.path.append(".")
from app.core.config import settings

client = genai.Client(api_key=settings.GEMINI_API_KEY)

text = "This is a test startup idea description."
model = "gemini-embedding-001"

print(f"Generating embedding with output_dimensionality=1536...")
try:
    from google.genai import types
    response = client.models.embed_content(
        model=model,
        contents=text,
        config=types.EmbedContentConfig(
            output_dimensionality=1536
        )
    )
    if hasattr(response, "embedding") and response.embedding:
        values = response.embedding.values
        print(f"Dimension: {len(values)}")
except Exception as e:
    print(f"Error: {e}")
