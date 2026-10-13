# Kairos promo — Acts 2–6

Remotion project for the 2:30 section of the Kairos promo that follows the existing 25 s problem cut.

```bash
npm i
npm run dev          # Studio preview
npx remotion render KairosPromo out/kairos-promo-act2-6.mp4 --codec=h264 --crf=18
```

## Audio (all generated locally, nothing to license)

```bash
cd tools
python3 -m venv .venv && .venv/bin/pip install kokoro-onnx soundfile numpy scipy
mkdir -p models && cd models
curl -LO https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
curl -LO https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
cd .. && .venv/bin/python vo.py        # voiceover -> public/vo, src/vo-durations.json
.venv/bin/python sound.py              # SFX + music bed -> public/sfx, public/music.wav
```

`src/timeline.json` is the single source of timing for voiceover cues, SFX hits and the music arrangement.
Change a cue there, then re-run `sound.py` so the music ducking follows.

## Before sharing

- `rootCauseSeconds` (default 12) in `src/Root.tsx` drives the "0:12" root-cause timer. Replace it with a measured run.
- Demo values come from seeded customer data in `backend/app/*.csv`, with name and login masked.
