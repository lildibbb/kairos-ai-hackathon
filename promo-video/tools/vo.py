"""Voiceover lines for the Kairos promo, generated locally with Kokoro (Apache-2.0 TTS)."""
import json
import os
import sys

import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro

HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "..", "public", "vo")
VOICE = os.environ.get("VOICE", "af_heart")
SPEED = float(os.environ.get("SPEED", "0.94"))

LINES = {
    "vo01": "What if every technician knew the next move... before they even arrived?",
    "vo02": "Meet Kairos. Next Best Action.",
    "vo03": "One engine reads the whole line. So your team doesn't have to.",
    "vo04": "Router. Wi-Fi. Fibre. Devices. Usage. All checked at once.",
    "vo05": "It finds the cause. Tells you what to do. And spots the right upgrade.",
    "vo06": "Here's a real ticket. The customer says the internet is slow.",
    "vo07": "Kairos pulls the router, Wi-Fi and fibre data, and checks every likely cause, together.",
    "vo08": "Root cause found. Not twenty-five minutes. Seconds.",
    "vo09": "Then, one clear next best action. Reboot the router remotely first. Go on site only if it's still needed.",
    "vo10": "And because the cause is weak coverage, it recommends the upgrade that actually fixes it.",
    "vo11": "Fixed right. The first time.",
    "vo12": "About two hours back, per field team, every day.",
    "vo13": "Built to push First Fix Right above ninety percent.",
    "vo14": "Every repeat visit avoided saves an estimated sixty-two ringgit.",
    "vo15": "And every one percent of ARPU is worth about fifty-one million a year.",
    "vo16": "This is only the start. The same engine can power EasyFix in My Unifi, the call centre, live chat, and our stores.",
    "vo17": "Kairos. Know the next move, even before you arrive.",
}

kokoro = Kokoro(os.path.join(HERE, "models", "kokoro-v1.0.onnx"), os.path.join(HERE, "models", "voices-v1.0.bin"))
os.makedirs(OUT, exist_ok=True)
only = sys.argv[1:]
durations = {}
for key, text in LINES.items():
    if only and key not in only:
        continue
    samples, rate = kokoro.create(text.replace("ARPU", "A R P U"), voice=VOICE, speed=SPEED, lang="en-us")
    samples = np.asarray(samples, dtype=np.float32)
    # Trim leading/trailing near-silence so lines land on their cue, then normalise to -1 dBFS peak.
    loud = np.where(np.abs(samples) > 0.01)[0]
    if loud.size:
        samples = samples[max(0, loud[0] - int(0.03 * rate)): loud[-1] + int(0.15 * rate)]
    samples = samples / (np.max(np.abs(samples)) + 1e-9) * 0.89
    sf.write(os.path.join(OUT, f"{key}.wav"), samples, rate)
    durations[key] = round(len(samples) / rate, 3)
    print(key, durations[key])

path = os.path.join(HERE, "..", "src", "vo-durations.json")
existing = json.load(open(path)) if os.path.exists(path) else {}
existing.update(durations)
json.dump(existing, open(path, "w"), indent=2)
