# Implementation Guide

## Quick Start Implementation

### Phase 1: Basic Prototype (1-2 Hours)

#### Step 1: Environment Setup
```bash
# Create project directory
mkdir mike_logger
cd mike_logger

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install whisper pyaudio anthropic python-dotenv
```

#### Step 2: Test Whisper Installation
```bash
# Test Whisper with a sample file
python -c "import whisper; model = whisper.load_model('base'); print('Whisper loaded successfully')"
```

#### Step 3: Basic Audio Capture Test
```python
# test_audio.py
import pyaudio
import wave

def test_microphone():
    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000
    RECORD_SECONDS = 5
    
    p = pyaudio.PyAudio()
    
    stream = p.open(format=FORMAT,
                    channels=CHANNELS,
                    rate=RATE,
                    input=True,
                    frames_per_buffer=CHUNK)
    
    print("Recording 5 seconds...")
    frames = []
    
    for _ in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
        data = stream.read(CHUNK)
        frames.append(data)
    
    stream.stop_stream()
    stream.close()
    p.terminate()
    
    # Save test file
    with wave.open("test_recording.wav", "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))
    
    print("Recording saved as test_recording.wav")

if __name__ == "__main__":
    test_microphone()
```

#### Step 4: Basic STT Test
```python
# test_stt.py
import whisper

def test_whisper():
    model = whisper.load_model("base")
    result = model.transcribe("test_recording.wav")
    print(f"Transcription: {result['text']}")
    return result['text']

if __name__ == "__main__":
    test_whisper()
```

### Phase 2: Core Implementation (2-4 Hours)

#### Step 1: Audio Capture Module
```python
# src/audio_capture.py
import pyaudio
import wave
import threading
import queue
import time
from datetime import datetime
import os

class AudioCapture:
    def __init__(self, chunk_size=1024, sample_rate=16000, channels=1):
        self.chunk_size = chunk_size
        self.sample_rate = sample_rate
        self.channels = channels
        self.format = pyaudio.paInt16
        
        self.audio_queue = queue.Queue()
        self.is_recording = False
        self.audio_thread = None
        
        # Create data directory
        os.makedirs("data/audio", exist_ok=True)
    
    def start_recording(self):
        """Start continuous audio recording"""
        self.is_recording = True
        self.audio_thread = threading.Thread(target=self._record_audio)
        self.audio_thread.start()
        print("Audio recording started...")
    
    def stop_recording(self):
        """Stop audio recording"""
        self.is_recording = False
        if self.audio_thread:
            self.audio_thread.join()
        print("Audio recording stopped.")
    
    def _record_audio(self):
        """Internal recording loop"""
        p = pyaudio.PyAudio()
        
        try:
            stream = p.open(
                format=self.format,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size
            )
            
            segment_frames = []
            segment_duration = 30  # seconds
            frames_per_segment = int(self.sample_rate * segment_duration / self.chunk_size)
            
            while self.is_recording:
                data = stream.read(self.chunk_size)
                segment_frames.append(data)
                
                # Save segment every 30 seconds
                if len(segment_frames) >= frames_per_segment:
                    self._save_segment(segment_frames)
                    segment_frames = []
                    
        except Exception as e:
            print(f"Recording error: {e}")
        finally:
            stream.stop_stream()
            stream.close()
            p.terminate()
    
    def _save_segment(self, frames):
        """Save audio segment to file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"data/audio/segment_{timestamp}.wav"
        
        p = pyaudio.PyAudio()
        with wave.open(filename, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(p.get_sample_size(self.format))
            wf.setframerate(self.sample_rate)
            wf.writeframes(b''.join(frames))
        
        # Queue for processing
        self.audio_queue.put(filename)
        print(f"Saved audio segment: {filename}")
        
        p.terminate()
    
    def get_next_audio_file(self):
        """Get next audio file for processing"""
        try:
            return self.audio_queue.get_nowait()
        except queue.Empty:
            return None
```

#### Step 2: Speech-to-Text Module
```python
# src/speech_to_text.py
import whisper
import os
import json
from datetime import datetime

class SpeechToText:
    def __init__(self, model_size="base"):
        print(f"Loading Whisper model: {model_size}")
        self.model = whisper.load_model(model_size)
        
        # Create output directory
        os.makedirs("data/transcripts", exist_ok=True)
    
    def transcribe_file(self, audio_file):
        """Transcribe a single audio file"""
        if not os.path.exists(audio_file):
            print(f"Audio file not found: {audio_file}")
            return None
        
        try:
            result = self.model.transcribe(audio_file)
            
            # Create transcript data
            transcript = {
                "audio_file": audio_file,
                "timestamp": datetime.now().isoformat(),
                "text": result["text"],
                "segments": result["segments"],
                "language": result["language"]
            }
            
            # Save transcript
            transcript_file = self._save_transcript(transcript)
            
            # Clean up audio file after processing
            os.remove(audio_file)
            
            return transcript_file
            
        except Exception as e:
            print(f"Transcription error: {e}")
            return None
    
    def _save_transcript(self, transcript):
        """Save transcript to JSON file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"data/transcripts/transcript_{timestamp}.json"
        
        with open(filename, "w") as f:
            json.dump(transcript, f, indent=2)
        
        print(f"Saved transcript: {filename}")
        return filename
```

#### Step 3: Task Processor Module
```python
# src/task_processor.py
import json
import os
from datetime import datetime
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

class TaskProcessor:
    def __init__(self):
        self.client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        os.makedirs("data/tasks", exist_ok=True)
    
    def process_transcript(self, transcript_file):
        """Process transcript and extract tasks"""
        with open(transcript_file, "r") as f:
            transcript = json.load(f)
        
        text = transcript["text"]
        if not text or len(text.strip()) < 10:
            print("Transcript too short, skipping...")
            return None
        
        # Extract tasks using Claude
        tasks = self._extract_tasks(text)
        
        if tasks:
            # Save tasks
            task_file = self._save_tasks(tasks, transcript_file)
            return task_file
        
        return None
    
    def _extract_tasks(self, text):
        """Use Claude to extract tasks from text"""
        prompt = f"""
        Analyze this conversation transcript and extract actionable items:
        
        {text}
        
        Please identify:
        1. Specific tasks or action items
        2. Ideas worth exploring
        3. Questions that need answers
        4. Important reminders or deadlines
        
        Return a JSON array of objects with this structure:
        {{
            "type": "task|idea|question|reminder",
            "content": "description",
            "priority": "high|medium|low",
            "deadline": "YYYY-MM-DD or null",
            "status": "pending"
        }}
        
        Only return the JSON array, nothing else.
        """
        
        try:
            response = self.client.messages.create(
                model="claude-3-sonnet-20240229",
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Parse JSON response
            tasks_text = response.content[0].text.strip()
            if tasks_text.startswith("```json"):
                tasks_text = tasks_text[7:-3]
            elif tasks_text.startswith("```"):
                tasks_text = tasks_text[3:-3]
            
            tasks = json.loads(tasks_text)
            print(f"Extracted {len(tasks)} items from transcript")
            return tasks
            
        except Exception as e:
            print(f"Task extraction error: {e}")
            return None
    
    def _save_tasks(self, tasks, transcript_file):
        """Save extracted tasks to file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"data/tasks/tasks_{timestamp}.json"
        
        task_data = {
            "timestamp": datetime.now().isoformat(),
            "source_transcript": transcript_file,
            "tasks": tasks
        }
        
        with open(filename, "w") as f:
            json.dump(task_data, f, indent=2)
        
        print(f"Saved tasks: {filename}")
        return filename
```

#### Step 4: Main Orchestrator
```python
# src/main.py
import time
import threading
import signal
import sys
from audio_capture import AudioCapture
from speech_to_text import SpeechToText
from task_processor import TaskProcessor

class MikeLogger:
    def __init__(self):
        self.audio_capture = AudioCapture()
        self.stt = SpeechToText()
        self.task_processor = TaskProcessor()
        
        self.running = True
        self.processing_thread = None
    
    def start(self):
        """Start the Mike Logger system"""
        print("Starting Mike Logger...")
        
        # Start audio capture
        self.audio_capture.start_recording()
        
        # Start processing thread
        self.processing_thread = threading.Thread(target=self._processing_loop)
        self.processing_thread.start()
        
        # Set up signal handler for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        
        print("Mike Logger is running. Press Ctrl+C to stop.")
        
        # Keep main thread alive
        while self.running:
            time.sleep(1)
    
    def _processing_loop(self):
        """Main processing loop"""
        while self.running:
            # Check for new audio files
            audio_file = self.audio_capture.get_next_audio_file()
            
            if audio_file:
                print(f"Processing audio file: {audio_file}")
                
                # Transcribe audio
                transcript_file = self.stt.transcribe_file(audio_file)
                
                if transcript_file:
                    # Extract tasks
                    task_file = self.task_processor.process_transcript(transcript_file)
                    
                    if task_file:
                        print(f"Tasks extracted: {task_file}")
            
            # Sleep before checking again
            time.sleep(5)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signal"""
        print("\nShutting down Mike Logger...")
        self.running = False
        self.audio_capture.stop_recording()
        
        if self.processing_thread:
            self.processing_thread.join()
        
        print("Mike Logger stopped.")
        sys.exit(0)

if __name__ == "__main__":
    logger = MikeLogger()
    logger.start()
```

#### Step 5: Configuration and Environment
```bash
# .env file
ANTHROPIC_API_KEY=your_api_key_here
```

```python
# requirements.txt
whisper
pyaudio
anthropic
python-dotenv
```

```python
# config.py
import os

class Config:
    # Audio settings
    CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 1024))
    SAMPLE_RATE = int(os.getenv("SAMPLE_RATE", 16000))
    CHANNELS = int(os.getenv("CHANNELS", 1))
    
    # Whisper settings
    WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
    
    # Processing settings
    AUDIO_SEGMENT_DURATION = int(os.getenv("AUDIO_SEGMENT_DURATION", 30))
    PROCESSING_INTERVAL = int(os.getenv("PROCESSING_INTERVAL", 5))
    
    # Data retention
    KEEP_AUDIO_FILES = os.getenv("KEEP_AUDIO_FILES", "false").lower() == "true"
    TRANSCRIPT_RETENTION_DAYS = int(os.getenv("TRANSCRIPT_RETENTION_DAYS", 30))
```

### Phase 3: Testing and Validation (1-2 Hours)

#### Step 1: Unit Tests
```python
# tests/test_audio_capture.py
import unittest
import tempfile
import os
from src.audio_capture import AudioCapture

class TestAudioCapture(unittest.TestCase):
    def setUp(self):
        self.audio_capture = AudioCapture()
    
    def test_initialization(self):
        self.assertIsNotNone(self.audio_capture)
        self.assertEqual(self.audio_capture.sample_rate, 16000)
    
    def test_start_stop_recording(self):
        self.audio_capture.start_recording()
        self.assertTrue(self.audio_capture.is_recording)
        
        self.audio_capture.stop_recording()
        self.assertFalse(self.audio_capture.is_recording)

if __name__ == "__main__":
    unittest.main()
```

#### Step 2: Integration Test
```python
# test_integration.py
import os
import time
from src.main import MikeLogger

def test_end_to_end():
    """Test the complete pipeline with a sample audio file"""
    # Create a test instance
    logger = MikeLogger()
    
    # Test with a sample recording
    print("Testing complete pipeline...")
    
    # You would need to provide a test audio file
    # or record one for testing
    
    print("Integration test complete!")

if __name__ == "__main__":
    test_end_to_end()
```

### Phase 4: Production Enhancements (2-4 Hours)

#### Step 1: Add Voice Activity Detection
```python
# src/voice_activity_detection.py
import webrtcvad
import numpy as np

class VoiceActivityDetector:
    def __init__(self, sample_rate=16000, aggressiveness=2):
        self.vad = webrtcvad.Vad(aggressiveness)
        self.sample_rate = sample_rate
        self.frame_duration = 30  # ms
        self.frame_size = int(sample_rate * frame_duration / 1000)
    
    def is_speech(self, audio_data):
        """Check if audio contains speech"""
        # Convert to appropriate format for VAD
        audio_int16 = np.frombuffer(audio_data, dtype=np.int16)
        
        # Process in frames
        frames = self._frame_generator(audio_int16)
        speech_frames = 0
        total_frames = 0
        
        for frame in frames:
            total_frames += 1
            if self.vad.is_speech(frame, self.sample_rate):
                speech_frames += 1
        
        # Return True if >30% of frames contain speech
        return speech_frames / total_frames > 0.3 if total_frames > 0 else False
    
    def _frame_generator(self, audio_data):
        """Generate frames for VAD processing"""
        for i in range(0, len(audio_data), self.frame_size):
            frame = audio_data[i:i + self.frame_size]
            if len(frame) == self.frame_size:
                yield frame.tobytes()
```

#### Step 2: Add Logging and Monitoring
```python
# src/logger.py
import logging
import os
from datetime import datetime

def setup_logging():
    """Set up logging configuration"""
    os.makedirs("logs", exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(f"logs/mike_logger_{datetime.now().strftime('%Y%m%d')}.log"),
            logging.StreamHandler()
        ]
    )
    
    return logging.getLogger(__name__)
```

#### Step 3: Add Configuration Management
```python
# src/config_manager.py
import json
import os
from typing import Dict, Any

class ConfigManager:
    def __init__(self, config_path="config.json"):
        self.config_path = config_path
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file"""
        default_config = {
            "audio": {
                "sample_rate": 16000,
                "channels": 1,
                "chunk_size": 1024,
                "segment_duration": 30
            },
            "whisper": {
                "model": "base",
                "language": "en"
            },
            "processing": {
                "interval": 5,
                "use_vad": True,
                "vad_aggressiveness": 2
            },
            "retention": {
                "keep_audio": False,
                "transcript_days": 30,
                "task_days": 365
            }
        }
        
        if os.path.exists(self.config_path):
            with open(self.config_path, "r") as f:
                user_config = json.load(f)
                # Merge with defaults
                self._merge_config(default_config, user_config)
        
        return default_config
    
    def _merge_config(self, default: Dict, user: Dict):
        """Recursively merge user config with defaults"""
        for key, value in user.items():
            if key in default and isinstance(default[key], dict) and isinstance(value, dict):
                self._merge_config(default[key], value)
            else:
                default[key] = value
    
    def get(self, key_path: str, default=None):
        """Get configuration value by dot notation (e.g., 'audio.sample_rate')"""
        keys = key_path.split('.')
        value = self.config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
    
    def save(self):
        """Save current configuration to file"""
        with open(self.config_path, "w") as f:
            json.dump(self.config, f, indent=2)
```

### Deployment Instructions

#### Local Development
```bash
# Clone and setup
git clone <repository>
cd mike_logger
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your API keys

# Run
python src/main.py
```

#### Docker Deployment
```dockerfile
# Dockerfile
FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    portaudio19-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application
COPY src/ ./src/
COPY config.json .

# Create data directories
RUN mkdir -p data/audio data/transcripts data/tasks logs

# Run application
CMD ["python", "src/main.py"]
```

```yaml
# docker-compose.yml
version: '3.8'
services:
  mike-logger:
    build: .
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
      - ./config.json:/app/config.json
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    devices:
      - /dev/snd:/dev/snd  # Audio device access
    restart: unless-stopped
```

### Next Steps

1. **Test the basic implementation** with short recordings
2. **Add error handling** and recovery mechanisms
3. **Implement data retention policies**
4. **Add web interface** for task management
5. **Scale to production** with proper monitoring

This implementation provides a solid foundation that can be extended based on your specific needs and requirements.