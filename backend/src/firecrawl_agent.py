import os
from firecrawl import FirecrawlApp
from dotenv import load_dotenv

load_dotenv()

class FirecrawlAgent:
    def __init__(self):
        # Firecrawl uses FIRECRAWL_API_KEY from env automatically
        api_key = os.getenv("FIRECRAWL_API_KEY")
        if not api_key:
            print("WARNING: FIRECRAWL_API_KEY is missing. Scraping will use mocked/fallback data.")
            self.app = None
        else:
            self.app = FirecrawlApp(api_key=api_key)

    def search_and_scrape(self, query: str, limit: int = 3) -> str:
        """
        Runs a web search using Firecrawl and returns the extracted content 
        of the top results as markdown.
        """
        if not self.app:
            return f"Mocked competitor data for: {query}\n\n- Competitor X: Strong features but highly priced.\n- Competitor Y: Cheaper but lacks AI integration."
        
        try:
            print(f"Firecrawl: Searching for '{query}'...")
            search_results = self.app.search(
                query=query,
                page_options={
                    "fetchPageContent": True 
                }
            )

            results_md = []
            results_list = search_results.get("data", [])
            for item in results_list[:limit]:
                title = item.get("title", "No Title")
                url = item.get("url", "No URL")
                content = item.get("markdown", "No content available")
                
                results_md.append(f"### Source: {title} ({url})\n{content[:2000]}...\n")
                
            return "\n".join(results_md)

        except Exception as e:
            print(f"Error during Firecrawl search: {e}")
            return f"Failed to gather competitor data. Error: {str(e)}"
