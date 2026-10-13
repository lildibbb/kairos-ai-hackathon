"""Synthesises every sound effect and the music bed for the Kairos promo.

Everything is generated from scratch (no samples), so there is nothing to license.
The music follows src/timeline.json and ducks itself under the voiceover lines.
"""
import json
import os

import numpy as np
import soundfile as sf
from scipy.signal import butter, fftconvolve, sosfilt

SR = 48000
HERE = os.path.dirname(__file__)
ROOT = os.path.join(HERE, "..")
SFX_DIR = os.path.join(ROOT, "public", "sfx")
TIMELINE = json.load(open(os.path.join(ROOT, "src", "timeline.json")))
VO_DUR = json.load(open(os.path.join(ROOT, "src", "vo-durations.json")))
rng = np.random.default_rng(7)


# ---------- building blocks ----------

def t_axis(seconds):
    return np.arange(int(seconds * SR)) / SR


def filt(x, kind, freq, order=2):
    nyq = SR / 2
    if kind == "band":
        sos = butter(order, [max(20, freq[0]) / nyq, min(freq[1], nyq * 0.95) / nyq], btype="band", output="sos")
    else:
        sos = butter(order, min(freq, nyq * 0.95) / nyq, btype=kind, output="sos")
    return sosfilt(sos, x, axis=0)


def env_ad(n, attack, decay, curve=4.0):
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    d = np.exp(-curve * np.clip(t - attack, 0, None) / max(decay, 1e-4))
    return a * d


def noise(seconds):
    return rng.standard_normal(int(seconds * SR))


def sweep_filtered_noise(seconds, f0, f1, bands=10, width=0.6):
    """Noise whose band-pass centre glides from f0 to f1 (crossfaded filter bank)."""
    n = int(seconds * SR)
    src = noise(seconds)
    centres = np.geomspace(f0, f1, bands) if f0 > 0 and f1 > 0 else np.linspace(f0, f1, bands)
    pos = np.linspace(0, bands - 1, n)
    out = np.zeros(n)
    for i, c in enumerate(centres):
        band = filt(src, "band", (c * (1 - width / 2), c * (1 + width / 2)))
        weight = np.clip(1 - np.abs(pos - i), 0, 1)
        out += band * weight
    return out


def glide_sine(seconds, f0, f1, curve=6.0):
    t = t_axis(seconds)
    f = f1 + (f0 - f1) * np.exp(-curve * t)
    return np.sin(2 * np.pi * np.cumsum(f) / SR)


def reverb(x, seconds=2.2, mix=0.3, tone=6000, pre=0.012):
    n = int(seconds * SR)
    t = np.arange(n) / SR
    ir_l = rng.standard_normal(n) * np.exp(-6.5 * t / seconds)
    ir_r = rng.standard_normal(n) * np.exp(-6.5 * t / seconds)
    ir = np.stack([ir_l, ir_r], 1)
    ir = filt(ir, "low", tone)
    ir[: int(pre * SR)] = 0
    ir /= np.sqrt(np.sum(ir ** 2, axis=0, keepdims=True))
    mono = x if x.ndim == 1 else x.mean(1)
    wet = np.stack([fftconvolve(mono, ir[:, 0]), fftconvolve(mono, ir[:, 1])], 1)
    dry = stereo(x)
    out = np.zeros((max(len(wet), len(dry)), 2))
    out[: len(dry)] += dry * (1 - mix)
    out[: len(wet)] += wet * mix
    return out


def stereo(x, pan=0.0):
    if x.ndim == 2:
        return x
    left = np.cos((pan + 1) * np.pi / 4)
    right = np.sin((pan + 1) * np.pi / 4)
    return np.stack([x * left, x * right], 1) * np.sqrt(2)


def normalise(x, peak=0.89):
    m = np.max(np.abs(x))
    return x if m == 0 else x / m * peak


def fade(x, fin=0.002, fout=0.02):
    x = x.copy()
    a, b = int(fin * SR), int(fout * SR)
    if a:
        x[:a] *= np.linspace(0, 1, a)[:, None] if x.ndim == 2 else np.linspace(0, 1, a)
    if b:
        x[-b:] *= np.linspace(1, 0, b)[:, None] if x.ndim == 2 else np.linspace(1, 0, b)
    return x


def save(name, x, peak=0.89):
    sf.write(os.path.join(SFX_DIR, f"{name}.wav"), fade(normalise(stereo(x), peak)), SR)


# ---------- sound effects ----------

def sfx_low_note():
    d = 4.5
    t = t_axis(d)
    tone = np.sin(2 * np.pi * 55 * t) + 0.45 * np.sin(2 * np.pi * 110 * t) + 0.12 * np.sin(2 * np.pi * 165.5 * t)
    tone = np.tanh(1.6 * tone) * env_ad(len(t), 0.04, 3.2, 3.0)
    return reverb(tone, 3.0, 0.35, 2500)


def sfx_shimmer():
    d = 2.6
    t = t_axis(d)
    x = np.zeros_like(t)
    for f in (2093, 2637, 3136, 3951, 5274, 6272):
        x += np.sin(2 * np.pi * f * t + rng.uniform(0, 6)) * (1 + 0.5 * np.sin(2 * np.pi * rng.uniform(5, 9) * t))
    x *= np.clip(t / 1.2, 0, 1) ** 2 * np.exp(-1.4 * np.clip(t - 1.2, 0, None))
    x = filt(x, "high", 1500) * 0.4 + filt(noise(d), "high", 7000) * 0.05 * np.clip(t / 1.2, 0, 1)
    return reverb(x, 2.8, 0.55, 9000)


def sfx_riser():
    d = 2.2
    t = t_axis(d)
    sw = sweep_filtered_noise(d, 250, 7000, 12, 0.5)
    tone = sum(np.sin(2 * np.pi * np.cumsum(220 * 2 ** (2.2 * t / d) * k) / SR) / k for k in (1, 2, 3))
    amp = (t / d) ** 2.2
    x = (sw * 0.5 + tone * 0.25) * amp
    return reverb(x, 1.4, 0.25, 8000)[: int(d * SR)]


def sfx_whoosh(d=0.95, f0=300, f1=5000):
    t = t_axis(d)
    x = sweep_filtered_noise(d, f0, f1, 10, 0.8)
    shape = np.sin(np.pi * np.clip(t / d, 0, 1)) ** 2.5
    x *= shape
    pan = np.linspace(-0.7, 0.7, len(t))
    st = np.stack([x * np.cos((pan + 1) * np.pi / 4), x * np.sin((pan + 1) * np.pi / 4)], 1)
    return reverb(st, 1.0, 0.2, 7000)


def sfx_whoosh_up():
    return sfx_whoosh(0.6, 600, 9000)


def sfx_tick():
    d = 0.18
    t = t_axis(d)
    body = np.sin(2 * np.pi * 2350 * t) * np.exp(-t / 0.018) + 0.5 * np.sin(2 * np.pi * 4700 * t) * np.exp(-t / 0.008)
    click = filt(noise(d), "high", 5000) * np.exp(-t / 0.002) * 0.6
    return reverb(body + click, 0.5, 0.12, 9000)


def sfx_hit(size=1.0, tail=2.4):
    d = 1.6 * size + 0.4
    t = t_axis(d)
    sub = glide_sine(d, 160, 42, 9) * env_ad(len(t), 0.002, 0.9 * size, 3.2)
    punch = filt(noise(d), "band", (120, 2400)) * np.exp(-t / 0.05) * 0.9
    snap = filt(noise(d), "high", 3500) * np.exp(-t / 0.012) * 0.5
    metal = sum(np.sin(2 * np.pi * f * t) for f in (311, 467, 829, 1243)) * np.exp(-t / 0.35) * 0.06
    x = np.tanh(1.8 * (sub * 1.1 + punch + snap + metal))
    return reverb(x, tail, 0.32, 5000)


def sfx_impact_soft():
    d = 2.0
    t = t_axis(d)
    sub = glide_sine(d, 90, 38, 4) * env_ad(len(t), 0.01, 1.4, 3)
    body = filt(noise(d), "low", 600) * env_ad(len(t), 0.005, 0.25, 4) * 0.5
    return reverb(np.tanh(1.4 * (sub + body)), 2.0, 0.3, 3000)


def sfx_impact_big():
    x = sfx_hit(1.5, 3.6)
    shimmer = sfx_shimmer()
    out = np.zeros((max(len(x), len(shimmer)), 2))
    out[: len(x)] += x
    out[: len(shimmer)] += shimmer * 0.35
    return out


def sfx_thud():
    d = 0.6
    t = t_axis(d)
    sub = glide_sine(d, 130, 55, 18) * env_ad(len(t), 0.001, 0.22, 4)
    click = filt(noise(d), "band", (900, 4000)) * np.exp(-t / 0.006) * 0.35
    return reverb(np.tanh(2 * (sub + click)), 0.7, 0.18, 5000)


def sfx_buzz():
    d = 0.42
    t = t_axis(d)
    motor = np.sign(np.sin(2 * np.pi * 172 * t)) * 0.4 + np.sin(2 * np.pi * 172 * t)
    motor = filt(motor, "band", (100, 1800)) * (0.6 + 0.4 * np.sin(2 * np.pi * 28 * t))
    motor *= np.clip(t / 0.02, 0, 1) * np.clip((d - t) / 0.04, 0, 1)
    return reverb(motor, 0.4, 0.1, 4000)


def bell(freq, d, decay=1.2, bright=1.0):
    t = t_axis(d)
    x = np.zeros_like(t)
    for ratio, amp, dec in ((1, 1, 1), (2.756, 0.45 * bright, 0.55), (5.404, 0.25 * bright, 0.3), (8.93, 0.1 * bright, 0.18)):
        x += amp * np.sin(2 * np.pi * freq * ratio * t) * np.exp(-t / (decay * dec))
    return x * np.clip(t / 0.003, 0, 1)


def sfx_ping():
    d = 2.6
    t = t_axis(d)
    x = bell(1760, d, 1.0) * 0.7 + bell(2637, d, 0.7, 0.6) * 0.3
    thump = glide_sine(d, 120, 50, 20) * env_ad(len(t), 0.001, 0.2, 4) * 0.8
    return reverb(x + thump, 2.4, 0.4, 9000)


def sfx_chime():
    d = 3.0
    a = bell(1318.5, d, 1.1)
    b = np.zeros_like(a)
    off = int(0.11 * SR)
    b[off:] = bell(1975.5, d, 1.3)[: len(a) - off]
    return reverb((a + b) * 0.6, 2.6, 0.42, 9000)


def sfx_chime_final():
    d = 5.0
    t = t_axis(d)
    x = np.zeros_like(t)
    for i, f in enumerate((880.0, 1108.7, 1318.5, 1760.0)):
        off = int(i * 0.14 * SR)
        x[off:] += bell(f, d, 1.8, 0.7)[: len(x) - off] * 0.5
    pad = sum(np.sin(2 * np.pi * f * t) for f in (110, 164.8, 220, 277.2)) * env_ad(len(t), 0.4, 3.5, 3) * 0.12
    return reverb(x + pad, 3.6, 0.5, 8000)


def sfx_reverse():
    d = 1.8
    t = t_axis(d)
    cym = filt(noise(d), "high", 4000) * np.exp(-t / 0.5) + bell(660, d, 0.8, 1.4) * 0.15
    return reverb(cym, 1.6, 0.4, 10000)[::-1][-int(d * SR):]


# ---------- music ----------

BPM = 120
BEAT = 60 / BPM
MUSIC_START = 10.0
CHORDS = [(57, 60, 64), (53, 57, 60), (48, 52, 55), (55, 59, 62)]  # Am F C G (MIDI)
ROOTS = [45, 41, 36, 43]


def midi(n):
    return 440 * 2 ** ((n - 69) / 12)


def saw(freq, t, detune=0.0):
    ph = (freq * (1 + detune)) * t
    return 2 * (ph - np.floor(ph + 0.5))


def section_level(t):
    """Per-layer gain curves (0..1) over the 150 s timeline."""
    def ramp(a, b, v0, v1):
        return np.clip((t - a) / max(b - a, 1e-6), 0, 1) * (v1 - v0) + v0

    def window(a, b, fi=0.05, fo=0.05):
        return np.clip((t - a) / fi, 0, 1) * np.clip((b - t) / fo, 0, 1)

    groove = window(36, 57, 0.02, 0.4) + window(60, 97.4, 0.02, 0.25) + window(126, 145, 0.02, 0.6)
    pulse = window(10, 97.4, 1.5, 0.25) + window(119, 145, 2.0, 0.5)
    pad = window(10, 97.6, 2.5, 0.4) + window(119, 150, 2.5, 4.5)
    hats = window(22, 57, 1.0, 0.3) + window(60, 97.4, 0.2, 0.2) + window(124, 145, 1.0, 0.3)
    bright = np.clip(ramp(10, 34, 0.0, 0.7) + window(36, 57, 0.01, 0.01) * 0.3 + window(60, 97, 0.01, 0.2) * 0.35
                     + window(86, 97, 1.0, 0.2) * 0.3 + ramp(119, 137, 0, 0.6) * (t < 145) + window(137, 145, 0.01, 0.3) * 0.4, 0, 1)
    arp = window(44, 57, 1.0, 0.3) + window(62, 97.4, 1.0, 0.2) + window(130, 145, 1.0, 0.3)
    swell = window(86, 97.4, 2.5, 0.3) + window(137, 150, 0.2, 4.5)
    dip = 1 - 0.8 * window(57, 60.5, 0.15, 0.6)
    return dict(groove=groove, pulse=pulse, pad=pad, hats=hats, bright=bright, arp=arp, swell=swell, dip=dip)


def vo_duck(t):
    env = np.zeros_like(t)
    for key, start in TIMELINE["vo"].items():
        end = start + VO_DUR.get(key, 3)
        env = np.maximum(env, np.clip((t - start + 0.15) / 0.15, 0, 1) * np.clip((end + 0.45 - t) / 0.45, 0, 1))
    return 1 - 0.55 * env  # about -7 dB under speech


def kick_at(n, d=0.42):
    t = np.arange(n) / SR
    body = glide_sine(n / SR, 150, 46, 30) * np.exp(-t / 0.16)
    click = filt(rng.standard_normal(n), "band", (1500, 6000)) * np.exp(-t / 0.004) * 0.3
    return np.tanh(2.2 * (body + click))


def build_music(total):
    n = int(total * SR)
    t = np.arange(n) / SR
    L = section_level(t)
    beat_pos = (t - MUSIC_START) / BEAT
    bar = np.floor(beat_pos / 4).astype(int) % 4
    since_beat = (beat_pos - np.floor(beat_pos)) * BEAT
    pump = 1 - 0.62 * np.exp(-since_beat / 0.11) * np.clip(L["groove"], 0, 1)

    # Pad: detuned saws on the bar chord, crossfading a dark and a bright filter.
    pad = np.zeros(n)
    for i, chord in enumerate(CHORDS):
        mask = (bar == i).astype(float)
        mask = filt(mask, "low", 6)  # smooth chord changes
        voice = sum(saw(midi(note), t, dt) for note in chord for dt in (-0.004, 0.0, 0.005)) / 9
        pad += voice * mask
    pad_dark = filt(pad, "low", 700)
    pad_bright = filt(pad, "low", 3800)
    pad = pad_dark * (1 - L["bright"]) + pad_bright * L["bright"]
    pad *= L["pad"] * 0.42 * pump

    # Pulse bass: eighth notes on the bar root.
    eighth = (beat_pos * 2) - np.floor(beat_pos * 2)
    gate = np.exp(-eighth * BEAT / 2 / 0.12)
    root = np.zeros(n)
    for i, r in enumerate(ROOTS):
        root += (bar == i) * midi(r)
    phase = np.cumsum(root) / SR
    bass_raw = 2 * (phase - np.floor(phase + 0.5)) * 0.7 + np.sin(2 * np.pi * phase) * 0.6
    bass = filt(bass_raw, "low", 900) * (1 - L["bright"]) * 0.6 + filt(bass_raw, "low", 2200) * L["bright"]
    bass *= gate * L["pulse"] * 0.5 * pump

    # Drums.
    drums = np.zeros(n)
    kick_len = int(0.42 * SR)
    k = kick_at(kick_len)
    clap_src = filt(rng.standard_normal(int(0.25 * SR)), "band", (900, 5000))
    clap = clap_src * np.exp(-np.arange(len(clap_src)) / SR / 0.06)
    hat_src = filt(rng.standard_normal(int(0.08 * SR)), "high", 8000)
    hat = hat_src * np.exp(-np.arange(len(hat_src)) / SR / 0.018)
    first_beat = int(np.ceil((0 - MUSIC_START) / BEAT))
    beats = np.arange(first_beat, int(total / BEAT) + 4)
    hats_track = np.zeros(n)
    for b in beats:
        start = MUSIC_START + b * BEAT
        s = int(start * SR)
        if s < 0 or s >= n:
            continue
        g = L["groove"][s]
        if g > 0.01:
            e = min(n, s + kick_len)
            drums[s:e] += k[: e - s] * g
            if b % 2 == 1:
                e = min(n, s + len(clap))
                drums[s:e] += clap[: e - s] * 0.45 * g
        for sub in range(4):
            ss = int((start + sub * BEAT / 4) * SR)
            if 0 <= ss < n and L["hats"][ss] > 0.01:
                vel = (0.55 if sub == 2 else 0.22) * L["hats"][ss]
                e = min(n, ss + len(hat))
                hats_track[ss:e] += hat[: e - ss] * vel
    # Snare roll into the drops.
    for roll_end in (36.0, 126.0, 137.0):
        for j in range(16):
            tt = roll_end - 2 * BEAT + j * BEAT / 8
            s = int(tt * SR)
            e = min(n, s + len(clap))
            drums[s:e] += clap[: e - s] * (0.08 + 0.32 * j / 15)

    # Arp: sixteenth-note plucks across chord tones, an octave up.
    arp = np.zeros(n)
    pluck_len = int(0.22 * SR)
    pt = np.arange(pluck_len) / SR
    for b in beats:
        for sub in range(4):
            start = MUSIC_START + b * BEAT + sub * BEAT / 4
            s = int(start * SR)
            if s < 0 or s >= n or L["arp"][s] < 0.01:
                continue
            chord = CHORDS[int(np.floor(((start - MUSIC_START) / BEAT) / 4)) % 4]
            note = chord[(b * 4 + sub) % 3] + 12 + (12 if sub == 3 else 0)
            p = (np.sign(np.sin(2 * np.pi * midi(note) * pt)) * 0.3 + np.sin(2 * np.pi * midi(note) * pt)) * np.exp(-pt / 0.07)
            e = min(n, s + pluck_len)
            arp[s:e] += p[: e - s] * 0.16 * L["arp"][s]
    arp = filt(arp, "low", 5000)
    # Dotted-eighth delay for width.
    delay = int(BEAT * 0.75 * SR)
    arp_l = arp.copy()
    arp_r = np.zeros(n)
    arp_r[delay:] += arp[:-delay] * 0.55
    arp_l[2 * delay:] += arp[:-2 * delay] * 0.3

    # Swell: airy high strings for the upsell moment and the finale.
    swell = np.zeros(n)
    for i, chord in enumerate(CHORDS):
        swell += (bar == i) * sum(np.sin(2 * np.pi * midi(note + 12) * t + 0.3 * np.sin(2 * np.pi * 5.2 * t)) for note in chord)
    swell = filt(swell, "low", 5000) * L["swell"] * 0.12

    mono_bed = pad + bass + swell
    st = stereo(mono_bed) + np.stack([arp_l, arp_r], 1) + stereo(drums * 0.9) + np.stack([hats_track * 0.8, hats_track], 1) * 0.6
    st = reverb(st, 2.6, 0.18, 6000)[:n]
    st *= (L["dip"] * vo_duck(t))[:, None]
    # Final resolve: a held A-minor-add9 with a long fade.
    end = t >= 145
    st[end] *= np.clip((150 - t[end]) / 5.0, 0, 1)[:, None] ** 1.5
    st = np.tanh(1.2 * st)
    return normalise(st, 0.8)


SFX = {
    "low_note": sfx_low_note, "shimmer": sfx_shimmer, "riser": sfx_riser, "whoosh": sfx_whoosh,
    "whoosh_up": sfx_whoosh_up, "tick": sfx_tick, "hit": sfx_hit, "impact_soft": sfx_impact_soft,
    "impact_big": sfx_impact_big, "thud": sfx_thud, "buzz": sfx_buzz, "ping": sfx_ping,
    "chime": sfx_chime, "chime_final": sfx_chime_final, "reverse": sfx_reverse,
}

if __name__ == "__main__":
    os.makedirs(SFX_DIR, exist_ok=True)
    for name, fn in SFX.items():
        save(name, fn())
        print("sfx", name)
    music = build_music(TIMELINE["duration"])
    sf.write(os.path.join(ROOT, "public", "music.wav"), fade(music, 0.01, 0.5), SR)
    print("music", round(len(music) / SR, 2), "s")
