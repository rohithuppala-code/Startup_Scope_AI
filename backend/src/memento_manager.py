import os
from mem0 import Memory
from mem0.memory.setup import setup_config

class MementoManager:
    def __init__(self):
        # We initialize mem0 to use a simple local vector database by default 
        # (ChromaDB or similar). It will persist memories locally under 
        # a `.mem0/` directory.
        try:
            self.memory = Memory()
        except Exception as e:
            print(f"Mem0 could not be initialized. Using fallback dict. Error: {e}")
            self.memory = None
            self.fallback_db = {}

    def fetch_history(self, user_id: str, query: str = "") -> str:
        """
        Retrieves the past history / pivots of the user.
        """
        if not self.memory:
            return "\n".join(self.fallback_db.get(user_id, []))
            
        print(f"Memento: Fetching history for user {user_id}")
        try:
            # We fetch all memories for the user
            memories = self.memory.search(query="Previous startup ideas and pivots", user_id=user_id, limit=5)
            
            if not memories:
                return "No previous history found for this user."
                
            history_str = []
            for mem in memories:
                history_str.append(f"- {mem['memory']}")
            return "\n".join(history_str)
        except Exception as e:
            print(f"Error reading from Memento: {e}")
            return "Could not retrieve historical context due to an error."

    def append_history(self, user_id: str, text: str):
        """
        Adds a new memory fragment (or summary of evaluation) for a user.
        """
        if not self.memory:
            if user_id not in self.fallback_db:
                self.fallback_db[user_id] = []
            self.fallback_db[user_id].append(text)
            return

        print(f"Memento: Saving new evaluation to history for user {user_id}")
        self.memory.add(messages=text, user_id=user_id)
