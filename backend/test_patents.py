import asyncio
from app.services.patents import _query_uspto
patents = _query_uspto(["machine learning", "language model"])
print(f"Found {len(patents)} patents")
