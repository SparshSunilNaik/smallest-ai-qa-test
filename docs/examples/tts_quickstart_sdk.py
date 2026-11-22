# Requires: pip install smallestai
from smallestai import SmallestAI

client = SmallestAI()  # reads SMALLEST_API_KEY from the environment

audio_chunks = client.waves.synthesize_tts(
    text="Modern problems require modern solutions.",
    voice_id="meher",
    model="lightning_v3.1_pro",
    sample_rate=24000,
    speed=1.0,
    output_format="wav",
)

with open("output.wav", "wb") as f:
    f.write(b"".join(audio_chunks))
print("Saved output.wav")
