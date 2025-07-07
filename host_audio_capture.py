#!/usr/bin/env python3
"""
Native audio capture for Mac host.
Saves audio files to shared volume for Docker processing.
"""
import pyaudio
import webrtcvad
import wave
import time
import os
import signal
import sys
import threading
import collections
import numpy as np
from datetime import datetime
from pathlib import Path

class HostAudioCapture:
    def __init__(self):
        self.sample_rate = 16000
        self.chunk_size = 1024
        self.channels = 1
        self.format = pyaudio.paInt16
        
        # VAD for intelligent segmentation
        self.vad = webrtcvad.Vad(2)  # Aggressiveness 0-3
        self.frame_duration_ms = 30  # VAD frame size
        self.frames_per_vad_frame = int(self.sample_rate * self.frame_duration_ms / 1000)
        
        # Segmentation parameters
        self.min_segment_duration = 5.0   # seconds
        self.max_segment_duration = 120.0 # seconds
        self.silence_threshold = 2.0      # seconds to trigger split
        self.speech_pad_ms = 300          # padding around speech
        
        # Ring buffer for VAD analysis
        self.ring_buffer_size = int(self.silence_threshold * 1000 / self.frame_duration_ms)
        self.ring_buffer = collections.deque(maxlen=self.ring_buffer_size)
        
        # Audio buffer
        self.audio_buffer = []
        self.segment_start_time = time.time()
        self.is_recording = False
        self.triggered = False
        
        # Ensure output directory exists
        self.output_dir = Path("data/audio")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        print(f"\n🛑 Received signal {signum}, stopping capture...")
        self.is_recording = False
        
    def list_audio_devices(self):
        """List available audio input devices"""
        p = pyaudio.PyAudio()
        
        print("Available audio input devices:")
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if info['maxInputChannels'] > 0:
                print(f"  [{i}] {info['name']} - {info['maxInputChannels']} channels")
        
        p.terminate()
        
    def is_speech(self, frame):
        """Check if audio frame contains speech using VAD"""
        try:
            # Convert frame to appropriate format for VAD
            if len(frame) == self.frames_per_vad_frame * 2:  # 16-bit = 2 bytes per sample
                return self.vad.is_speech(frame, self.sample_rate)
        except:
            pass
        return False
        
    def should_segment(self):
        """Determine if we should create a segment boundary"""
        if not self.ring_buffer:
            return False
            
        # Check current segment duration
        segment_duration = time.time() - self.segment_start_time
        
        # Force segmentation at max duration
        if segment_duration >= self.max_segment_duration:
            return True
            
        # Only consider segmentation after minimum duration
        if segment_duration < self.min_segment_duration:
            return False
            
        # Count recent speech frames
        num_speech = sum(self.ring_buffer)
        speech_ratio = num_speech / len(self.ring_buffer)
        
        # Segment if mostly silence
        return speech_ratio < 0.1
        
    def save_segment(self, frames):
        """Save audio segment to shared volume"""
        if not frames:
            return
            
        # Check minimum duration
        duration = len(frames) * self.chunk_size / self.sample_rate
        if duration < self.min_segment_duration:
            print(f"⏩ Skipping short segment ({duration:.1f}s)")
            return
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        filename = self.output_dir / f"segment_{timestamp}.wav"
        
        # Calculate audio statistics
        audio_data = np.frombuffer(b''.join(frames), dtype=np.int16)
        energy_mean = float(np.mean(np.abs(audio_data)))
        energy_std = float(np.std(np.abs(audio_data)))
        
        # Skip very quiet segments
        if energy_mean < 100:  # Threshold for silence
            print(f"🔇 Skipping silent segment ({duration:.1f}s, energy: {energy_mean:.0f})")
            return
        
        # Write WAV file
        try:
            with wave.open(str(filename), 'wb') as wf:
                wf.setnchannels(self.channels)
                wf.setsampwidth(2)  # 2 bytes = 16 bit
                wf.setframerate(self.sample_rate)
                wf.writeframes(b''.join(frames))
            
            print(f"📁 Saved: {filename.name} ({duration:.1f}s, energy: {energy_mean:.0f})")
            
        except Exception as e:
            print(f"❌ Error saving {filename.name}: {e}")
            
    def start_capture(self):
        """Start continuous audio capture with intelligent segmentation"""
        print("🎤 Mike Logger - Audio Capture Starting...")
        print(f"   Sample Rate: {self.sample_rate} Hz")
        print(f"   Channels: {self.channels}")
        print(f"   Output Directory: {self.output_dir}")
        print(f"   Segment Range: {self.min_segment_duration}-{self.max_segment_duration}s")
        print()
        
        # List available devices
        self.list_audio_devices()
        print()
        
        # Get device index from environment or use default
        device_index = os.getenv('AUDIO_DEVICE_INDEX')
        if device_index:
            try:
                device_index = int(device_index)
                print(f"Using audio device index: {device_index}")
            except ValueError:
                print(f"Invalid device index: {device_index}, using default")
                device_index = None
        
        p = pyaudio.PyAudio()
        
        try:
            stream = p.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=self.chunk_size
            )
            
            print("🎙️  Recording started... (Press Ctrl+C to stop)")
            print("   Files will be saved automatically when speech segments are detected")
            print("   Docker containers will process them for transcription and task extraction")
            print()
            
            self.is_recording = True
            self.segment_start_time = time.time()
            
            while self.is_recording:
                try:
                    # Read audio chunk
                    data = stream.read(self.chunk_size, exception_on_overflow=False)
                    self.audio_buffer.append(data)
                    
                    # VAD analysis on appropriately sized frames
                    if len(data) >= self.frames_per_vad_frame * 2:
                        # Take first part of chunk for VAD
                        vad_frame = data[:self.frames_per_vad_frame * 2]
                        is_speech_frame = self.is_speech(vad_frame)
                        self.ring_buffer.append(is_speech_frame)
                        
                        # Show activity indicator
                        audio_array = np.frombuffer(data, dtype=np.int16)
                        volume = np.abs(audio_array).mean()
                        activity = "🔊" if is_speech_frame else "🔇"
                        bar = "█" * min(20, int(volume / 200))
                        print(f"\r{activity} Volume: {bar:<20} {volume:>6.0f}", end="", flush=True)
                        
                        # Check for segmentation
                        if self.should_segment():
                            self.save_segment(self.audio_buffer)
                            self.audio_buffer = []
                            self.segment_start_time = time.time()
                            print()  # New line after segment
                            
                except Exception as e:
                    print(f"\n❌ Error reading audio: {e}")
                    break
                    
        except Exception as e:
            print(f"❌ Error opening audio stream: {e}")
            print("   Check that your microphone is connected and not in use by another application")
            
        finally:
            try:
                stream.stop_stream()
                stream.close()
            except:
                pass
            p.terminate()
            
            # Save any remaining audio
            if self.audio_buffer:
                print("\n💾 Saving final segment...")
                self.save_segment(self.audio_buffer)
                
            print("\n🛑 Audio capture stopped")

def main():
    """Main entry point"""
    print("🎤 Mike Logger - Host Audio Capture")
    print("=" * 50)
    
    capture = HostAudioCapture()
    
    try:
        capture.start_capture()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()