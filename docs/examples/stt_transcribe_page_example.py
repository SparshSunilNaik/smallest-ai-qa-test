import requests

with open("./call.wav", "rb") as f:
    audio = f.read()

r = requests.post(
    "https://api.smallest.ai/waves/v1/stt/",
    params={"model": "pulse-pro", "language": "en", "word_timestamps": "true"},
    headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/octet-stream"},
    data=audio,
)
r.raise_for_status()
print(r.json()["transcription"])
