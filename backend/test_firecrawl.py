import os
import sys

from dotenv import load_dotenv
load_dotenv("/Users/likhith./Startup_Scope_AI/backend/.env")

from firecrawl import FirecrawlApp

def test_search():
    try:
        app = FirecrawlApp(api_key=os.environ.get("FIRECRAWL_API_KEY"))
        res = app.search(query="Top CRM software 2024", limit=1, scrape_options={"formats": ["markdown"], "onlyMainContent": True})
        if hasattr(res, "web"):
            print("res.web type:", type(res.web))
            for item in res.web:
                print(type(item))
                if hasattr(item, "model_dump"):
                    print("Keys:", list(item.model_dump().keys()))
                else:
                    print("Item:", item)
        else:
            print("No web attribute.")
    except Exception as e:
        print("Exception:", e)

if __name__ == "__main__":
    test_search()
