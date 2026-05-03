import asyncio
import os
import sys

# Set up the environment for testing
sys.path.append("/Users/likhith./Startup_Scope_AI/backend")
os.environ["OTEL_CONSOLE_EXPORT"] = "false"

from app.core.config import settings
from google import genai
from firecrawl import FirecrawlApp

async def main():
    print("\n" + "="*50)
    print("🔍 DIAGNOSTIC TEST: External API Providers")
    print("="*50)

    # 1. Test Gemini API Key
    print("\n--- 1. Testing Gemini API Key ---")
    try:
        if not settings.GEMINI_API_KEY:
            print("❌ GEMINI_API_KEY is not set in environment!")
        else:
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            print(f"✅ Gemini Client Initialized (Key ends in ...{settings.GEMINI_API_KEY[-4:]})")
            
            # Simple test generation
            print("⏳ Attempting a simple completion (gemini-2.0-flash)...")
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents="Reply with the word 'PONG'."
            )
            print(f"✅ Gemini Response Success: {response.text.strip()}")
    except Exception as e:
        print(f"❌ Gemini API Test Failed: {e}")

    # 2. Test Firecrawl API Key
    print("\n--- 2. Testing Firecrawl API ---")
    try:
        if not settings.FIRECRAWL_API_KEY:
            print("❌ FIRECRAWL_API_KEY is not set in environment!")
        else:
            fc_client = FirecrawlApp(api_key=settings.FIRECRAWL_API_KEY)
            print(f"✅ Firecrawl Client Initialized (Key ends in ...{settings.FIRECRAWL_API_KEY[-4:]})")
            
            # Simple scrape test
            print("⏳ Attempting a simple scrape (https://example.com)...")
            scrape_result = fc_client.scrape_url("https://example.com")
            
            if "markdown" in scrape_result:
                print(f"✅ Firecrawl Scrape Success! Length: {len(scrape_result['markdown'])} chars")
            else:
                print(f"⚠️ Firecrawl Scrape returned unknown format: {list(scrape_result.keys())}")
                
            # Optional: Test search/crawl if needed (scrape is usually enough to verify the key works)
            print("⏳ Attempting a search test...")
            search_result = fc_client.search("Y Combinator Top Startups 2024", timeout=15000, limit=2)
            if search_result and "data" in search_result:
                print(f"✅ Firecrawl Search Success! Found {len(search_result['data'])} results.")
            else:
                print(f"❌ Firecrawl Search Failed or returned empty: {search_result}")

    except Exception as e:
        print(f"❌ Firecrawl API Test Failed: {e}")

    print("\n" + "="*50)
    print("🏁 Diagnostics Complete")
    print("="*50 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
