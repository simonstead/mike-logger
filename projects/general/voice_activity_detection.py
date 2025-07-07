"""
Voice Activity Detection (VAD) for Audio Segmentation

This script implements a basic voice activity detection algorithm to improve audio segmentation.
The goal is to identify speech segments within an audio recording, which can then be used to
better segment the audio into meaningful chunks.

The approach used here is a simple energy-based VAD, which looks at the short-term energy of the
audio signal to determine if a frame contains speech or not. More advanced techniques, such as
those using machine learning models, can also be employed for more robust VAD.

"""

import numpy as np
import scipy.signal as signal

def voice_activity_detection(audio, sample_rate, frame_size=0.025, frame_stride=0.01, energy_threshold=0.5):
    """
    Perform voice activity detection on the input audio signal.

    Args:
        audio (numpy.ndarray): The input audio signal.
        sample_rate (int): The sampling rate of the audio signal.
        frame_size (float): The size of the analysis frame in seconds.
        frame_stride (float): The stride between consecutive analysis frames in seconds.
        energy_threshold (float): The energy threshold to determine if a frame contains speech or not.

    Returns:
        numpy.ndarray: A binary mask indicating the speech/non-speech frames.
    """
    # Convert frame sizes from seconds to samples
    frame_size_samples = int(frame_size * sample_rate)
    frame_stride_samples = int(frame_stride * sample_rate)

    # Compute the short-term energy of the audio signal
    frames = [audio[i:i+frame_size_samples] for i in range(0, len(audio), frame_stride_samples)]
    energies = [np.sum(frame**2) / frame_size_samples for frame in frames]

    # Apply the energy threshold to determine speech/non-speech frames
    speech_mask = np.array([energy > energy_threshold * max(energies) for energy in energies])

    return speech_mask

# Example usage
import sounddevice as sd

# Record 5 seconds of audio
duration = 5
audio = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1)
sd.wait()

# Perform voice activity detection
speech_mask = voice_activity_detection(audio.flatten(), sample_rate)

# Print the speech/non-speech segments
print("Speech segments:")
for start, end in zip(np.where(speech_mask)[0] * frame_stride_samples, np.where(speech_mask)[0] * frame_stride_samples + frame_size_samples):
    print(f"Start: {start/sample_rate:.2f}s, End: {end/sample_rate:.2f}s")