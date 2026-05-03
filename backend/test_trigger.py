import requests
import uuid

req = {
    "idea_description": "A new platform for automated testing using LLMs " + str(uuid.uuid4()),
    "target_market": "Developers",
    "budget_constraints": "Low",
    "idempotency_key": str(uuid.uuid4())
}
res = requests.post("http://127.0.0.1:8000/api/v1/validate", json=req, headers={"x-user-id": "9e4bb566-da84-4e47-a67e-c68cc96752cd"})
print(res.status_code)
print(res.json())
