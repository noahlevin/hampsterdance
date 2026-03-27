"""Generate a hamster-dance-style melody as an MP3.

Uses a sped-up, bouncy melody similar to the original hamster dance
(which was a sped-up version of "Whistle Stop" by Roger Miller).

This generates an original melody in the same spirit — fast, bouncy,
and annoying in the best possible way.
"""

import struct
import math
import wave
import subprocess
import os

SAMPLE_RATE = 44100
DURATION = 16  # seconds (loops)
BPM = 200

def generate_tone(freq, duration, volume=0.3, sample_rate=SAMPLE_RATE):
    """Generate a sine wave tone."""
    samples = []
    n_samples = int(sample_rate * duration)
    for i in range(n_samples):
        t = i / sample_rate
        # Add slight vibrato for character
        vibrato = math.sin(2 * math.pi * 6 * t) * 5
        sample = volume * math.sin(2 * math.pi * (freq + vibrato) * t)
        # Quick fade in/out to avoid clicks
        envelope = min(1.0, i / 500, (n_samples - i) / 500)
        samples.append(sample * envelope)
    return samples


def note_freq(note_name):
    """Convert note name to frequency."""
    notes = {
        'C4': 261.63, 'D4': 293.66, 'E4': 329.63, 'F4': 349.23,
        'G4': 392.00, 'A4': 440.00, 'B4': 493.88,
        'C5': 523.25, 'D5': 587.33, 'E5': 659.25, 'F5': 698.46,
        'G5': 783.99, 'A5': 880.00, 'B5': 987.77,
        'C6': 1046.50, 'REST': 0,
    }
    return notes.get(note_name, 440)


# Bouncy, repetitive melody in the hamster dance spirit
# (original composition, not a cover)
melody = [
    # Main riff (repeat)
    ('E5', 0.12), ('G5', 0.12), ('A5', 0.12), ('G5', 0.12),
    ('E5', 0.12), ('G5', 0.12), ('A5', 0.24),
    ('E5', 0.12), ('G5', 0.12), ('A5', 0.12), ('G5', 0.12),
    ('E5', 0.12), ('D5', 0.12), ('C5', 0.24),

    ('D5', 0.12), ('E5', 0.12), ('D5', 0.12), ('C5', 0.12),
    ('D5', 0.12), ('E5', 0.24), ('REST', 0.12),
    ('E5', 0.12), ('G5', 0.12), ('A5', 0.12), ('G5', 0.12),
    ('E5', 0.12), ('D5', 0.12), ('C5', 0.24),

    # Variation
    ('C5', 0.12), ('D5', 0.12), ('E5', 0.12), ('G5', 0.12),
    ('A5', 0.12), ('G5', 0.12), ('E5', 0.12), ('G5', 0.12),
    ('A5', 0.24), ('G5', 0.12), ('E5', 0.12),
    ('D5', 0.12), ('C5', 0.12), ('D5', 0.24),

    ('E5', 0.12), ('E5', 0.12), ('G5', 0.12), ('A5', 0.12),
    ('B5', 0.12), ('A5', 0.12), ('G5', 0.12), ('E5', 0.12),
    ('D5', 0.12), ('E5', 0.24), ('C5', 0.12),
    ('D5', 0.12), ('E5', 0.12), ('REST', 0.24),
]

# Generate audio
all_samples = []
for note, dur in melody:
    freq = note_freq(note)
    if freq == 0:
        all_samples.extend([0.0] * int(SAMPLE_RATE * dur))
    else:
        all_samples.extend(generate_tone(freq, dur, volume=0.25))

# Loop to fill duration
loop_samples = all_samples[:]
while len(all_samples) < SAMPLE_RATE * DURATION:
    all_samples.extend(loop_samples)
all_samples = all_samples[:SAMPLE_RATE * DURATION]

# Write WAV
wav_path = 'hamsterdance.wav'
mp3_path = 'hamsterdance.mp3'

with wave.open(wav_path, 'w') as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(SAMPLE_RATE)
    for s in all_samples:
        s = max(-1.0, min(1.0, s))
        wav.writeframes(struct.pack('<h', int(s * 32767)))

print(f"Generated {wav_path} ({len(all_samples)/SAMPLE_RATE:.1f}s)")

# Convert to MP3 if ffmpeg is available
try:
    subprocess.run(
        ['ffmpeg', '-y', '-i', wav_path, '-b:a', '128k', mp3_path],
        capture_output=True, check=True
    )
    os.remove(wav_path)
    print(f"Converted to {mp3_path}")
except FileNotFoundError:
    print("ffmpeg not found — using WAV file instead")
    os.rename(wav_path, mp3_path.replace('.mp3', '.wav'))
