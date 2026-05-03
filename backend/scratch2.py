from google import genai
client = genai.Client(api_key="AIzaSyAiTsxqIoSttykRcXy64bIiPSPNtLMNkJA")
for m in client.models.list():
    if "flash" in m.name:
        print(m.name)
