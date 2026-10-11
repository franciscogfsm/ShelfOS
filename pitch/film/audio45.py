"""Original soundtrack and sound effects for the 45 s ShelfOS film, synthesised with NumPy
(no samples, no third-party music). 120 BPM, so every tap in the film lands on a beat.
Reads cues45.json written by `FILM=45 node render.mjs stills 0`.
Run: python audio45.py  ->  sound45.wav
"""
import json, wave
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
cues = json.loads((HERE / "cues45.json").read_text())
SR, DUR, BEAT = 48000, float(cues["duration"]), 0.5
N = int(SR * DUR)
t = np.arange(N) / SR
rng = np.random.default_rng(7)
music = np.zeros((2, N))  # ducked by the kick
fx = np.zeros((2, N))     # sound effects, never ducked


def add(bus, sig, at, gain=1.0, pan=0.0):
    i = int(at * SR)
    if i >= N or i < 0:
        return
    sig = sig[: N - i]
    bus[0, i : i + len(sig)] += sig * gain * (1 - max(0, pan))
    bus[1, i : i + len(sig)] += sig * gain * (1 + min(0, pan))


def hz(note):  # MIDI note -> frequency
    return 440 * 2 ** ((note - 69) / 12)


def tone(freqs, length, decay, attack=0.004):
    tt = np.arange(int(length * SR)) / SR
    freqs = np.atleast_1d(freqs)
    return sum(np.sin(2 * np.pi * f * tt) for f in freqs) / len(freqs) * np.exp(-tt * decay) * np.minimum(tt / attack, 1)


def bell(note, length=0.7, decay=6):
    f = hz(note)
    tt = np.arange(int(length * SR)) / SR
    return (np.sin(2 * np.pi * f * tt) + 0.4 * np.sin(2 * np.pi * 2.0 * f * tt) * np.exp(-tt * 6) + 0.2 * np.sin(2 * np.pi * 3.01 * f * tt) * np.exp(-tt * 12)) * np.exp(-tt * decay) * np.minimum(tt / 0.003, 1)


def smooth(x, width):
    w = np.hanning(width)
    return np.convolve(x, w / w.sum(), mode="same")


def swish(length, peak, bright=48):
    n = int(length * SR)
    x = smooth(rng.standard_normal(n), bright) - smooth(rng.standard_normal(n), 400) * 0.3
    tt = np.linspace(0, 1, n)
    return x * np.where(tt < peak, (tt / peak) ** 2.2, ((1 - tt) / (1 - peak)) ** 1.6)


# ── music ────────────────────────────────────────────────────────────────────
# One chord every 4 s; the closing mark lands on C.
CHORDS = [(0, 45, [57, 60, 64, 71]), (4, 41, [57, 60, 65, 69]), (8, 48, [55, 60, 64, 67]), (12, 43, [55, 59, 62, 67]),
          (16, 45, [57, 60, 64, 71]), (20, 41, [57, 60, 65, 69]), (24, 48, [55, 60, 64, 67]), (28, 43, [55, 59, 62, 67]),
          (32, 45, [57, 60, 64, 71]), (36, 41, [57, 60, 65, 69]), (40, 43, [55, 59, 62, 69]), (43.6, 48, [55, 60, 64, 72])]
QUIET = (36.0, 37.5)   # the phones rise without drums
DROP = 42.0            # the theme flip


def chord_at(time):
    return [c for c in CHORDS if c[0] <= time][-1]


def playing(b):
    return not (QUIET[0] <= b < QUIET[1]) and b < DROP


for start, root, notes in CHORDS:
    length = 1.6 if start > 43 else 4.4
    n = int(length * SR)
    tt = np.arange(n) / SR
    env = np.minimum(tt / (0.25 if start > 43 else 0.9), 1) * np.minimum((length - tt) / 0.9, 1)
    bright = 0.25 + 0.75 * min(1, start / 20)
    for k, note in enumerate(notes):
        f = hz(note)
        v = np.zeros(n)
        for h, amp in ((1, 1), (2, 0.32 * bright), (3, 0.16 * bright), (4, 0.07 * bright)):
            v += amp * (np.sin(2 * np.pi * f * h * 1.003 * tt + k) + np.sin(2 * np.pi * f * h * 0.997 * tt + 2 * k))
        add(music, v * env, start, 0.016, pan=(-0.35, 0.35, -0.15, 0.15)[k])

kt = np.arange(int(0.32 * SR)) / SR
kick = np.sin(2 * np.pi * (46 * kt + (120 - 46) / 28 * (1 - np.exp(-28 * kt)))) * np.exp(-kt * 11)
kick[:96] *= np.linspace(0, 1, 96)
drums = np.zeros((2, N))
duck = np.ones(N)
for b in np.arange(6.0, DROP, BEAT):
    if not playing(b):
        continue
    add(drums, kick, b, 0.5)
    i, n = int(b * SR), int(0.3 * SR)
    duck[i : i + n] = np.minimum(duck[i : i + n], 0.45 + 0.55 * np.linspace(0, 1, n) ** 0.7)

for b in np.arange(10.0, DROP, BEAT):  # off-beat bass on the chord root
    if playing(b):
        tt = np.arange(int(0.22 * SR)) / SR
        add(music, np.tanh(2.2 * np.sin(2 * np.pi * hz(chord_at(b)[1] - 12) * tt)) * np.exp(-tt * 9) * np.minimum(tt / 0.006, 1), b + BEAT / 2, 0.16)

hat_n = int(0.05 * SR)
for b in np.arange(15.5, DROP, BEAT / 4):  # hats: off-beats, then sixteenths from the test images on
    step = round((b % BEAT) / (BEAT / 4))
    if not playing(b) or (b < 25.5 and step != 2):
        continue
    noise = np.diff(rng.standard_normal(hat_n + 1))
    add(music, noise * np.exp(-np.arange(hat_n) / SR * (70 if step != 2 else 45)), b, 0.022 if step == 2 else 0.011, pan=0.25 if step % 2 else -0.25)

for j, b in enumerate(np.arange(20.0, DROP, BEAT / 2)):  # plucked arpeggio with a dotted echo
    if not playing(b):
        continue
    f = hz(chord_at(b)[2][(j * 3) % 4] + 12)
    v = tone([f], 0.35, 14, 0.003) + 0.35 * tone([2 * f], 0.35, 14, 0.003)
    g = 0.03 if b < 25.5 else 0.043
    add(music, v, b, g, pan=-0.3)
    add(music, v, b + 0.375, g * 0.45, pan=0.4)

# ── sound effects ────────────────────────────────────────────────────────────
# the two halves of the opening line
for i, at in enumerate(cues["words"]):
    add(fx, swish(0.7, 0.3, 90), at - 0.1, 0.10, pan=(-0.3, 0.3)[i])
    add(fx, bell((69, 76)[i], 1.4, 2.6), at, 0.05)

# cards arriving on the store wall: soft pops climbing in pitch
for i, at in enumerate(cues["cards"]):
    tt = np.arange(int(0.12 * SR)) / SR
    f0 = 420 * 2 ** (i / 7)
    add(fx, np.sin(2 * np.pi * (f0 * tt - 0.4 * f0 * tt ** 2 / 0.24)) * np.exp(-tt * 34) * np.minimum(tt / 0.002, 1), at, 0.10, pan=-0.5 + i / 6)

# taps: a glassy tick with a little weight under it
for i, at in enumerate(cues["taps"]):
    f = hz(chord_at(at)[2][3] + 24)
    tick = tone([f], 0.16, 55, 0.001) + 0.5 * tone([2.01 * f], 0.16, 90, 0.001)
    tick[:192] += 0.6 * rng.standard_normal(192) * np.linspace(1, 0, 192)
    add(fx, tick, at, 0.15, pan=(-0.2, 0.2)[i % 2])
    add(fx, tone([95], 0.16, 38, 0.002), at, 0.13)

# every view change: a short airy swish right after the tap
for at in cues["views"]:
    add(fx, swish(0.42, 0.35, 30), at + 0.02, 0.11, pan=-0.15)

# the day replay: a run of ticks climbing in pitch
start, step, count = cues["lapse"]
for i in range(count):
    add(fx, tone([hz(69 + i * 0.7) * 2], 0.06, 80, 0.001), start + i * step, 0.055, pan=-0.5 + i / count)

# tasks ticked off: two rising notes
for i, at in enumerate(cues["done"]):
    add(fx, bell(88 + i, 0.5, 9), at, 0.07, pan=0.2)
    add(fx, bell(93 + i, 0.7, 7), at + 0.075, 0.07, pan=0.25)

# search: one key per letter
start, step, count = cues["keys"]
for i in range(count):
    n = int(0.035 * SR)
    click = smooth(rng.standard_normal(n), 6) * np.exp(-np.arange(n) / SR * 160)
    add(fx, click, start + i * step, 0.5, pan=rng.uniform(-0.25, 0.25))
    add(fx, tone([rng.uniform(1500, 2100)], 0.03, 150, 0.0005), start + i * step, 0.035)
    add(fx, tone([170], 0.05, 70, 0.001), start + i * step, 0.06)

# the assistant: question sent, thinking, answer
tt = np.arange(int(0.16 * SR)) / SR
add(fx, np.sin(2 * np.pi * (520 * tt + 1900 * tt ** 2)) * np.exp(-tt * 16) * np.minimum(tt / 0.004, 1), cues["send"] + 0.04, 0.09, pan=0.3)
a, b = cues["think"]
n = int((b - a) * SR)
tt = np.arange(n) / SR
pulse = (0.5 - 0.5 * np.cos(2 * np.pi * 7 * tt)) ** 3
think = (np.sin(2 * np.pi * hz(81) * tt) + 0.5 * np.sin(2 * np.pi * hz(88) * tt)) * pulse * np.minimum(tt / 0.2, 1) * np.minimum((tt[-1] - tt) / 0.2, 1)
add(fx, think, a, 0.022, pan=0.35)
for i, note in enumerate((84, 88, 91, 95, 100)):
    add(fx, bell(note, 0.9, 5), cues["answer"] + i * 0.055, 0.045, pan=0.1 + i * 0.1)
add(fx, swish(0.5, 0.25, 20), cues["answer"] - 0.05, 0.07, pan=0.3)

# mobile: confirmation chime, then the toast
add(fx, bell(79, 0.8, 5), cues["confirm"], 0.08)
add(fx, bell(84, 1.0, 4), cues["confirm"] + 0.11, 0.08)
add(fx, tone([330], 0.1, 40, 0.002), cues["toast"], 0.10)

# big moves
for at in cues["whoosh"]:
    add(fx, swish(0.9, 0.62), at - 0.56, 0.2, pan=0.2)
tt = np.arange(int(1.2 * SR)) / SR
add(fx, np.sin(2 * np.pi * (220 * tt + 260 * tt ** 2)) * (tt / 1.2) ** 2, cues["flip"] - 1.2, 0.05)
add(fx, sum(bell(m, 1.6, 3.2) for m in (72, 76, 79, 84)), cues["flip"], 0.03)
tt = np.arange(int(1.4 * SR)) / SR
add(fx, np.sin(2 * np.pi * (38 * tt + 30 / 9 * (1 - np.exp(-9 * tt)))) * np.exp(-tt * 3.5), cues["end"], 0.4)
add(fx, sum(bell(m, 1.4, 2.2) for m in (60, 67, 72, 76, 79)), cues["end"], 0.022)

# ── mix ──────────────────────────────────────────────────────────────────────
dry = music * duck + drums + fx
ir_n = int(1.8 * SR)
ir = rng.standard_normal((2, ir_n)) * np.exp(-np.arange(ir_n) / SR * 3.6)
size = 1 << int(np.ceil(np.log2(N + ir_n)))
send = music * duck + fx * 1.3
wet = np.stack([np.fft.irfft(np.fft.rfft(send[c], size) * np.fft.rfft(ir[c], size), size)[:N] for c in range(2)])
wet /= np.abs(wet).max() + 1e-9
mix = dry + wet * np.abs(dry).max() * 0.22
fade = np.minimum(t / 0.05, 1) * np.minimum((DUR - t) / 0.5, 1)
mix = np.tanh(mix / np.abs(mix).max() * 1.6) * fade
mix *= 0.89 / np.abs(mix).max()
with wave.open(str(HERE / "sound45.wav"), "wb") as f:
    f.setnchannels(2)
    f.setsampwidth(2)
    f.setframerate(SR)
    f.writeframes((mix.T * 32767).astype("<i2").tobytes())
print(f"sound45.wav written: {DUR:.0f} s, peak {np.abs(mix).max():.2f}, rms {np.sqrt((mix ** 2).mean()):.3f}")
