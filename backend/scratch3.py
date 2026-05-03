from google import genai

client = genai.Client(api_key="AIzaSyAiTsxqIoSttykRcXy64bIiPSPNtLMNkJA")
models = ["gemini-2.5-flash", "gemini-flash-latest", "gemini-3.1-flash-lite-preview"]

for m in models:
    try:
        response = client.models.generate_content(
            model=m,
            contents='Hello'
        )
        print(f"{m} success:", response.text)
    except Exception as e:
        print(f"{m} failed:", str(e).split('\n')[0][:200])
