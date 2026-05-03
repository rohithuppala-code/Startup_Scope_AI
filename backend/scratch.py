import os
from google import genai

client = genai.Client(api_key="AIzaSyAiTsxqIoSttykRcXy64bIiPSPNtLMNkJA")
try:
    response = client.models.generate_content(
        model='gemini-2.0-flash',
        contents='Hello, testing 1 2 3'
    )
    print("gemini-2.0-flash success:", response.text)
except Exception as e:
    print("gemini-2.0-flash failed:", e)

try:
    response = client.models.generate_content(
        model='gemini-1.5-flash',
        contents='Hello, testing 1 2 3'
    )
    print("gemini-1.5-flash success:", response.text)
except Exception as e:
    print("gemini-1.5-flash failed:", e)
