from google import genai
import sys
sys.path.append(".")
from app.core.config import settings

client = genai.Client(api_key=settings.GEMINI_API_KEY)

text = "This is a test."
for model in ["models/embedding-001", "models/text-embedding-004", "gemini-embedding-001"]:
    print(f"Testing {model}...")
    try:
        res = client.models.embed_content(model=model, contents=text)
        if hasattr(res, "embedding"):
            print(f"  SUCCESS! Dim: {len(res.embedding.values)}")
        elif hasattr(res, "embeddings"):
            print(f"  SUCCESS! Dim: {len(res.embeddings[0].values)}")
    except Exception as e:
        print(f"  FAILED: {e}")
