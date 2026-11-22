import os
import requests

API_KEY = os.environ["SMALLEST_API_KEY"]

response = requests.post(
    "https://api.smallest.ai/waves/v1/tts",
    headers={
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "Accept": "audio/wav",
    },
    json={
        "text": "Modern problems require modern solutions.",
        "voice_id": "meher",
        "model": "lightning_v3.1_pro",
        "sample_rate": 24000,
        "speed": 1.0,
        "language": "en",
        "output_format": "wav",
    },
)

with open("output.wav", "wb") as f:
    f.write(response.content)
print(f"Saved output.wav ({len(response.content):,} bytes)")
