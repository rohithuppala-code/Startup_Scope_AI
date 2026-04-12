import os
import json
from openai import OpenAI
from pydantic import BaseModel

class LLMClient:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("WARNING: OPENAI_API_KEY is missing. Using mocked LLM responses.")
            self.client = None
        else:
            self.client = OpenAI(api_key=api_key)

    def generate_validation_report(self, system_prompt: str, user_prompt: str) -> dict:
        """
        Calls OpenAI API enforcing the JSON structure of ValidationReport.
        """
        if not self.client:
            return {
                "feasibility_score": 75.5,
                "competitor_analysis": "Mocked competitor analysis indicating medium saturation.",
                "identified_gaps": ["No AI integration", "Poor mobile UX"],
                "suggested_improvements": ["Add AI to the core product", "Build a React Native app"]
            }
            
        try:
            print("LLM: Generating validation report...")
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.2
            )
            
            content = response.choices[0].message.content
            return json.loads(content)
        except Exception as e:
            print(f"Error calling OpenAI API: {e}")
            return {
                "feasibility_score": 0.0,
                "competitor_analysis": "Failed to analyze due to API error.",
                "identified_gaps": [],
                "suggested_improvements": []
            }
