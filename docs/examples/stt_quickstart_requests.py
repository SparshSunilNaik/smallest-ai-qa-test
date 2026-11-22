import os
import requests

API_KEY = os.environ["SMALLEST_API_KEY"]
SAMPLE_URL = "https://github.com/smallest-inc/cookbook/raw/main/speech-to-text/getting-started/samples/audio.wav"

audio = requests.get(SAMPLE_URL).content

response = requests.post(
    "https://api.smallest.ai/waves/v1/stt/",
    params={"model": "pulse-pro", "language": "en"},
    headers={
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/octet-stream",
    },
    data=audio,
    timeout=120,
)

response.raise_for_status()
print(response.json()["transcription"])
