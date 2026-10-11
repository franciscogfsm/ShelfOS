"""Original soundtrack for the ShelfOS film, synthesised with NumPy (no samples, no third-party music).
120 BPM, so every tap in the film lands on a beat. Reads cues.json written by render.mjs.
Run: python audio.py  ->  sound.wav
"""
import json, wave
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
SR, DUR, BEAT = 48000, 30.0, 0.5
N = int(SR * DUR)
t = np.arange(N) / SR
rng = np.random.default_rng(7)
cues = json.loads((HERE / "cues.json").read_text())
L, R = np.zeros(N), np.zeros(N)


def add(sig, at, gain=1.0, pan=0.0):
    i = int(at * SR)
    if i >= N or i + len(sig) <= 0:
        return
    sig = sig[: N - i]
    L[i : i + len(sig)] += sig * gain * (1 - max(0, pan))
    R[i : i + len(sig)] += sig * gain * (1 + min(0, pan))


def hz(note):  # MIDI note -> frequency
    return 440 * 2 ** ((note - 69) / 12)


def fir_low(x, width):  # cheap smoothing filter
    return np.convolve(x, np.hanning(width) / np.hanning(width).sum(), mode="same")


# Chords, one every 4 s: Am9, Fmaj7, C, G, Am9, Fmaj7, G, then C for the closing mark.
CHORDS = [(0, 45, [57, 60, 64, 71]), (4, 41, [57, 60, 65, 69]), (8, 48, [55, 60, 64, 67]), (12, 43, [55, 59, 62, 67]),
          (16, 45, [57, 60, 64, 71]), (20, 41, [57, 60, 65, 69]), (24, 43, [55, 59, 62, 69]), (28, 48, [55, 60, 64, 72])]


def chord_at(time):
    return [c for c in CHORDS if c[0] <= time][-1]


# pad: soft detuned partials, opening up as the film goes on
for start, root, notes in CHORDS:
    length = (2.6 if start == 28 else 4.4)
    n = int(length * SR)
    tt = np.arange(n) / SR
    env = np.minimum(tt / 0.9, 1) * np.minimum((length - tt) / 0.9, 1)
    bright = 0.25 + 0.75 * min(1, start / 16)
    for k, note in enumerate(notes):
        f = hz(note)
        v = np.zeros(n)
        for h, amp in ((1, 1), (2, 0.32 * bright), (3, 0.16 * bright), (4, 0.07 * bright)):
            v += amp * (np.sin(2 * np.pi * f * h * 1.003 * tt + k) + np.sin(2 * np.pi * f * h * 0.997 * tt + 2 * k))
        add(v * env, start, 0.016, pan=(-0.35, 0.35, -0.15, 0.15)[k])

# kick on every beat once the day starts playing, out for the mobile entrance and the theme flip
kick_t = np.arange(int(0.32 * SR)) / SR
kick = np.sin(2 * np.pi * (46 * kick_t + (120 - 46) / 28 * (1 - np.exp(-28 * kick_t)))) * np.exp(-kick_t * 11)
kick[: int(0.002 * SR)] *= np.linspace(0, 1, int(0.002 * SR))
duck = np.ones(N)
for b in np.arange(4.0, 28.0, BEAT):
    if 21.5 <= b < 23.0 or b >= 26.75:
        continue
    add(kick, b, 0.5)
    i = int(b * SR)
    n = int(0.3 * SR)
    duck[i : i + n] = np.minimum(duck[i : i + n], 0.45 + 0.55 * np.linspace(0, 1, n) ** 0.7)

# bass: off-beat pulses on the chord root
for b in np.arange(7.0, 26.75, BEAT):
    if 21.5 <= b < 23.0:
        continue
    f = hz(chord_at(b)[1] - 12)
    n = int(0.22 * SR)
    tt = np.arange(n) / SR
    add(np.tanh(2.2 * np.sin(2 * np.pi * f * tt)) * np.exp(-tt * 9) * np.minimum(tt / 0.006, 1), b + BEAT / 2, 0.16)

# hats: off-beats from the tasks, sixteenths from the test images
hat_n = int(0.05 * SR)
for b in np.arange(10.0, 26.75, BEAT / 4):
    step = round((b % BEAT) / (BEAT / 4))
    if 21.5 <= b < 23.0 or (b < 16.5 and step != 2):
        continue
    noise = np.diff(rng.standard_normal(hat_n + 1))
    add(noise * np.exp(-np.arange(hat_n) / SR * (70 if step != 2 else 45)), b, 0.022 if step == 2 else 0.011, pan=0.25 if step % 2 else -0.25)

# plucked arpeggio with a dotted echo, from the analytics on
for j, b in enumerate(np.arange(13.0, 26.75, BEAT / 2)):
    if 21.5 <= b < 22.5:
        continue
    notes = chord_at(b)[2]
    f = hz(notes[(j * 3) % 4] + 12)
    n = int(0.35 * SR)
    tt = np.arange(n) / SR
    v = (np.sin(2 * np.pi * f * tt) + 0.35 * np.sin(2 * np.pi * 2 * f * tt)) * np.exp(-tt * 14) * np.minimum(tt / 0.003, 1)
    g = 0.03 if b < 16.5 else 0.045
    add(v, b, g, pan=-0.3)
    add(v, b + 0.375, g * 0.45, pan=0.4)

# taps: a short glassy tick with a little weight under it
for i, at in enumerate(cues["taps"]):
    n = int(0.16 * SR)
    tt = np.arange(n) / SR
    f = hz(chord_at(at)[2][3] + 24)
    tick = np.sin(2 * np.pi * f * tt) * np.exp(-tt * 55) + 0.5 * np.sin(2 * np.pi * 2.01 * f * tt) * np.exp(-tt * 90)
    tick[: int(0.004 * SR)] += 0.6 * rng.standard_normal(int(0.004 * SR)) * np.linspace(1, 0, int(0.004 * SR))
    thump = np.sin(2 * np.pi * 95 * tt) * np.exp(-tt * 38)
    add(tick, at, 0.14, pan=(-0.2, 0.2)[i % 2])
    add(thump, at, 0.12)

# the day replay: a run of soft ticks climbing in pitch
start, step, count = cues["lapse"]
for i in range(count):
    n = int(0.06 * SR)
    tt = np.arange(n) / SR
    add(np.sin(2 * np.pi * hz(69 + i * 0.7) * 2 * tt) * np.exp(-tt * 80), start + i * step, 0.05, pan=-0.5 + i / count)


def whoosh(length, peak):
    n = int(length * SR)
    x = fir_low(rng.standard_normal(n), 48) - fir_low(rng.standard_normal(n), 400) * 0.3
    tt = np.linspace(0, 1, n)
    env = np.where(tt < peak, (tt / peak) ** 2.2, ((1 - tt) / (1 - peak)) ** 1.6)
    return x * env


for at in cues["whoosh"]:
    add(whoosh(0.9, 0.62), at - 0.56, 0.2, pan=0.2)
# riser into the theme flip, then the flip itself and the landing of the closing mark
n = int(1.2 * SR)
tt = np.arange(n) / SR
add(np.sin(2 * np.pi * (220 * tt + 260 * tt ** 2)) * (tt / 1.2) ** 2, cues["flip"] - 1.2, 0.05)
n = int(1.4 * SR)
tt = np.arange(n) / SR
add(sum(np.sin(2 * np.pi * hz(m) * tt) for m in (72, 76, 79, 84)) * np.exp(-tt * 3.2), cues["flip"], 0.035)
add(np.sin(2 * np.pi * (38 * tt + 30 / 9 * (1 - np.exp(-9 * tt)))) * np.exp(-tt * 3.5), cues["end"], 0.4)
add(sum(np.sin(2 * np.pi * hz(m) * tt) for m in (60, 67, 72, 76, 79)) * np.exp(-tt * 2.2) * np.minimum(tt / 0.01, 1), cues["end"], 0.03)

# everything but the kick breathes with it
dry = np.stack([L, R])
dry *= duck

# room: decaying noise impulse response
ir_n = int(1.8 * SR)
ir = rng.standard_normal((2, ir_n)) * np.exp(-np.arange(ir_n) / SR * 3.6)
size = 1 << int(np.ceil(np.log2(N + ir_n)))
wet = np.stack([np.fft.irfft(np.fft.rfft(dry[c], size) * np.fft.rfft(ir[c], size), size)[:N] for c in range(2)])
wet /= np.abs(wet).max() + 1e-9
mix = dry + wet * np.abs(dry).max() * 0.22

fade = np.minimum(t / 0.05, 1) * np.minimum((DUR - t) / 0.5, 1)
mix = np.tanh(mix / np.abs(mix).max() * 1.6) * fade
mix *= 0.89 / np.abs(mix).max()
with wave.open(str(HERE / "sound.wav"), "wb") as f:
    f.setnchannels(2)
    f.setsampwidth(2)
    f.setframerate(SR)
    f.writeframes((mix.T * 32767).astype("<i2").tobytes())
rms = np.sqrt((mix ** 2).mean())
print(f"sound.wav written: peak {np.abs(mix).max():.2f}, rms {rms:.3f}")
