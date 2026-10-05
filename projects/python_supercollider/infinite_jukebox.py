import random
import numpy as np
import sounddevice as sd
import time

# Define chord progressions
chord_progressions = [
    ['C', 'F', 'G', 'C'],
    ['Am', 'F', 'C', 'G'],
    ['Dm', 'G', 'C', 'F'],
    ['Em', 'C', 'D', 'G'],
]

# Define all possible chords in chromatic order
chromatic_notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
major_chords = chromatic_notes
minor_chords = [note + 'm' for note in chromatic_notes]
all_chords = major_chords + minor_chords

# Note to frequency mapping (A4 = 440 Hz)
note_to_freq = {
    'C': 261.63,
    'C#': 277.18,
    'D': 293.66,
    'D#': 311.13,
    'E': 329.63,
    'F': 349.23,
    'F#': 369.99,
    'G': 392.00,
    'G#': 415.30,
    'A': 440.00,
    'A#': 466.16,
    'B': 493.88
}

# Chord to notes mapping
chord_to_notes = {
    # Major chords
    'C': ['C', 'E', 'G'],
    'C#': ['C#', 'F', 'G#'],
    'D': ['D', 'F#', 'A'],
    'D#': ['D#', 'G', 'A#'],
    'E': ['E', 'G#', 'B'],
    'F': ['F', 'A', 'C'],
    'F#': ['F#', 'A#', 'C#'],
    'G': ['G', 'B', 'D'],
    'G#': ['G#', 'C', 'D#'],
    'A': ['A', 'C#', 'E'],
    'A#': ['A#', 'D', 'F'],
    'B': ['B', 'D#', 'F#'],
    # Minor chords
    'Cm': ['C', 'D#', 'G'],
    'C#m': ['C#', 'E', 'G#'],
    'Dm': ['D', 'F', 'A'],
    'D#m': ['D#', 'F#', 'A#'],
    'Em': ['E', 'G', 'B'],
    'Fm': ['F', 'G#', 'C'],
    'F#m': ['F#', 'A', 'C#'],
    'Gm': ['G', 'A#', 'D'],
    'G#m': ['G#', 'B', 'D#'],
    'Am': ['A', 'C', 'E'],
    'A#m': ['A#', 'C#', 'F'],
    'Bm': ['B', 'D', 'F#']
}

# Add 7th chord extensions
for chord in list(chord_to_notes.keys()):
    if chord.endswith('m'):
        # Minor 7th
        root = chord[:-1]
        seventh_note = chromatic_notes[(chromatic_notes.index(root) + 10) % 12]
        chord_to_notes[chord + '7'] = chord_to_notes[chord] + [seventh_note]
    else:
        # Major 7th
        seventh_note = chromatic_notes[(chromatic_notes.index(chord) + 11) % 12]
        chord_to_notes[chord + '7'] = chord_to_notes[chord] + [seventh_note]

# Define harmony functions
def add_harmony(chord, harmony):
    new_chord = []
    for chord_name in chord:
        new_chord.append(chord_name)
        if harmony and random.random() < 0.5:  # Only add harmony to some chords
            new_chord.append(chord_name + harmony)
    return new_chord

def modulate_chord(chord_progression, step):
    new_progression = []
    for chord in chord_progression:
        # Extract root note and quality (major/minor)
        is_minor = chord.endswith('m')
        root = chord[:-1] if is_minor else chord
        
        # Handle special cases
        if root not in chromatic_notes:
            # Skip harmony extensions like '7', '9', etc.
            if chord in ['7', '9', '11', '13']:
                new_progression.append(chord)
                continue
            # Keep unknown chords as is
            new_progression.append(chord)
            continue
        
        # Find current position and transpose
        current_pos = chromatic_notes.index(root)
        new_pos = (current_pos + step) % 12
        new_root = chromatic_notes[new_pos]
        
        # Reconstruct chord with new root
        new_chord = new_root + 'm' if is_minor else new_root
        new_progression.append(new_chord)
    
    return new_progression

# Create the infinite jukebox
def infinite_jukebox():
    current_progression = random.choice(chord_progressions)
    while True:
        yield current_progression
        step = random.randint(-2, 2)
        current_progression = modulate_chord(current_progression, step)
        if random.random() < 0.2:
            current_progression = add_harmony(current_progression, random.choice(['7', '9', '11', '13']))

# Generate sine wave for a chord
def generate_chord_wave(chord_name, duration=0.5, sample_rate=44100):
    """Generate a sine wave for a chord"""
    t = np.linspace(0, duration, int(sample_rate * duration))
    wave = np.zeros_like(t)
    
    # Get notes for the chord
    if chord_name in chord_to_notes:
        notes = chord_to_notes[chord_name]
        for note in notes:
            if note in note_to_freq:
                freq = note_to_freq[note]
                # Add sine wave for this note
                wave += np.sin(2 * np.pi * freq * t)
        
        # Normalize
        wave = wave / len(notes) * 0.3  # Keep volume reasonable
    
    return wave

def play_chord_progression(progression, chord_duration=0.5):
    """Play a chord progression"""
    sample_rate = 44100
    
    for chord in progression:
        if chord in ['7', '9', '11', '13']:
            # Skip harmony extensions that aren't full chord names
            continue
            
        wave = generate_chord_wave(chord, chord_duration, sample_rate)
        sd.play(wave, sample_rate)
        sd.wait()  # Wait for the chord to finish

# Example usage
jukebox = infinite_jukebox()
print("Starting infinite jukebox... Press Ctrl+C to stop")
print()

try:
    for progression in jukebox:
        print(f"Playing: {progression}")
        play_chord_progression(progression, chord_duration=0.4)
        time.sleep(0.1)  # Small gap between progressions
except KeyboardInterrupt:
    print("\nStopping jukebox...")
    sd.stop()