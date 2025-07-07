# Architecture Documentation

## System Overview

The Mike Logger system consists of four main components working together to create an always-on voice assistant:

1. **Audio Capture Layer**: Continuous microphone input
2. **Speech Processing Layer**: Local STT conversion
3. **Intelligence Layer**: Task extraction and organization
4. **Action Layer**: Task execution and integration

## Detailed Architecture

### Minimal Prototype Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Microphone    │────│  Audio Buffer   │────│   Whisper STT   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                        │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Task System   │────│ Claude API      │────│   Text Queue    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

**Components:**
- **Audio Capture**: Python `pyaudio` with continuous recording
- **Intelligent Segmentation**: Smart boundaries based on speech patterns
- **STT Engine**: Whisper (base model) running locally
- **Processing**: Python scripts polling text queue
- **AI Integration**: Claude API for task extraction

**Resource Requirements:**
- CPU: 2+ cores (for real-time Whisper processing)
- RAM: 4GB+ (Whisper models + buffers)
- Storage: 100GB+ (for audio retention)
- Network: Minimal (only for Claude API calls)

### Secure Production Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Edge Device    │────│  Encrypted      │────│  Private Server │
│  (Wearable)     │    │  Transmission   │    │  (Self-hosted)  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                                              │
         │              ┌─────────────────┐            │
         └──────────────│  Local Agent    │────────────┘
                        │  (Your PC)      │
                        └─────────────────┘
```

**Security Features:**
- **End-to-End Encryption**: AES-256 with device-specific keys
- **Zero-Knowledge Server**: Cannot decrypt without device presence
- **Secure Transport**: WireGuard VPN tunnel
- **Data Retention**: Automatic deletion after processing
- **Access Control**: Certificate-based authentication

## Component Specifications

### Audio Capture Module

**Minimal Version:**
```python
# Continuous recording with pyaudio
CHUNK_SIZE = 1024
SAMPLE_RATE = 16000
CHANNELS = 1
FORMAT = pyaudio.paInt16
```

**Production Version:**
```python
# VAD-enabled capture
VAD_SENSITIVITY = 0.5
SILENCE_THRESHOLD = 2.0  # seconds
CHUNK_DURATION = 0.03    # 30ms chunks
```

**Key Features:**
- Voice Activity Detection (VAD) using `webrtcvad`
- Dynamic noise cancellation
- Automatic gain control
- Buffer overflow protection

### Speech-to-Text Module

**Whisper Model Selection:**
| Model | Size | RAM | Speed | Accuracy |
|-------|------|-----|-------|----------|
| tiny  | 39MB | 1GB | 32x   | Good     |
| base  | 74MB | 1GB | 16x   | Better   |
| small | 244MB| 2GB | 6x    | Great    |
| medium| 769MB| 5GB | 2x    | Excellent|

**Recommended Configuration:**
```python
# For real-time processing
model = whisper.load_model("base")
options = {
    "language": "en",
    "task": "transcribe",
    "temperature": 0.0,
    "no_speech_threshold": 0.6
}
```

### Intelligence Layer

**Task Extraction Pipeline:**
1. **Text Preprocessing**: Sentence segmentation, speaker identification
2. **Entity Recognition**: Identify names, dates, locations
3. **Action Classification**: Categorize statements (task, idea, question)
4. **Priority Scoring**: Urgency and importance analysis
5. **Context Linking**: Connect related conversations

**Claude Integration:**
```python
# Example prompt template
TASK_EXTRACTION_PROMPT = """
Analyze this conversation transcript and extract:
1. Action items with deadlines
2. Ideas worth exploring
3. Questions that need answers
4. Important information to remember

Format as structured JSON with priorities.
"""
```

### Data Storage

**Minimal Version:**
```
data/
├── audio/
│   ├── raw/           # Original recordings (temp)
│   └── processed/     # Post-VAD audio
├── transcripts/
│   ├── daily/         # Daily conversation logs
│   └── processed/     # Cleaned transcripts
└── tasks/
    ├── active/        # Current task list
    └── completed/     # Historical tasks
```

**Production Version:**
```sql
-- PostgreSQL schema
CREATE TABLE audio_sessions (
    id UUID PRIMARY KEY,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    file_path TEXT,
    encrypted_key TEXT
);

CREATE TABLE transcripts (
    id UUID PRIMARY KEY,
    session_id UUID REFERENCES audio_sessions(id),
    speaker_id TEXT,
    content TEXT,
    timestamp TIMESTAMP,
    confidence FLOAT
);

CREATE TABLE extracted_tasks (
    id UUID PRIMARY KEY,
    transcript_id UUID REFERENCES transcripts(id),
    content TEXT,
    priority INTEGER,
    status TEXT,
    created_at TIMESTAMP
);
```

## Security Model

### Encryption Architecture

**Data at Rest:**
- AES-256-GCM encryption for all audio files
- Separate key per device/session
- Master key stored in hardware security module

**Data in Transit:**
- TLS 1.3 for all HTTP communications
- WireGuard tunnel for audio transmission
- Certificate pinning for API endpoints

**Key Management:**
```python
# Device-specific key derivation
def derive_device_key(device_id, master_key):
    return PBKDF2(
        password=master_key,
        salt=device_id.encode(),
        iterations=100000,
        key_length=32
    )
```

### Privacy Controls

**Data Retention:**
- Audio files: 24 hours (configurable)
- Transcripts: 30 days (configurable)
- Tasks: Until manually deleted
- Logs: 7 days maximum

**Access Control:**
- Device certificates for authentication
- API rate limiting
- Audit logging for all access

## Performance Considerations

### Real-time Processing Requirements

**Latency Targets:**
- Audio capture to STT: < 2 seconds
- STT to task extraction: < 5 seconds
- End-to-end processing: < 10 seconds

**Optimization Strategies:**
1. **Streaming STT**: Process audio in chunks
2. **Model Quantization**: Reduce Whisper model size
3. **GPU Acceleration**: Use CUDA if available
4. **Background Processing**: Separate capture from processing

### Scalability

**Single User:**
- 8-10 hours daily recording
- ~100MB audio per day
- 10-50 tasks extracted daily

**Resource Scaling:**
```python
# Auto-scaling based on load
if cpu_usage > 80:
    reduce_whisper_quality()
if memory_usage > 90:
    flush_audio_buffers()
if storage_usage > 85:
    trigger_cleanup()
```

## Integration Points

### Claude API Integration

**Authentication:**
```python
import anthropic

client = anthropic.Anthropic(
    api_key="your-api-key"
)
```

**Task Processing:**
```python
def extract_tasks(transcript):
    response = client.messages.create(
        model="claude-3-sonnet-20240229",
        max_tokens=1000,
        messages=[{
            "role": "user", 
            "content": f"Extract tasks from: {transcript}"
        }]
    )
    return parse_tasks(response.content)
```

### Local System Integration

**File System Hooks:**
- Monitor specific directories for voice files
- Auto-process new recordings
- Update task management systems

**Notification System:**
- Desktop notifications for urgent tasks
- Email/SMS for high-priority items
- Calendar integration for deadlines

## Deployment Options

### Development Setup
```bash
# Local development
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py --mode development
```

### Production Deployment
```yaml
# docker-compose.yml
version: '3.8'
services:
  mike-logger:
    build: .
    environment:
      - MODE=production
      - WHISPER_MODEL=base
    volumes:
      - ./data:/app/data
      - ./config:/app/config
    ports:
      - "8080:8080"
```

### Cloud Deployment
```yaml
# kubernetes deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mike-logger
spec:
  replicas: 1
  selector:
    matchLabels:
      app: mike-logger
  template:
    metadata:
      labels:
        app: mike-logger
    spec:
      containers:
      - name: mike-logger
        image: mike-logger:latest
        resources:
          requests:
            memory: "4Gi"
            cpu: "2000m"
          limits:
            memory: "8Gi"
            cpu: "4000m"
```

## Future Enhancements

### Planned Features
1. **Multi-language Support**: Automatic language detection
2. **Speaker Recognition**: Personal voice model training
3. **Emotion Detection**: Sentiment analysis of conversations
4. **Context Awareness**: Location and time-based processing
5. **Proactive Suggestions**: AI-driven task recommendations

### Research Areas
1. **Federated Learning**: Improve models without sharing data
2. **Edge AI**: More processing on wearable devices
3. **Biometric Security**: Voice authentication
4. **Semantic Search**: Advanced conversation indexing

## Troubleshooting Guide

### Common Issues
1. **Audio Quality**: Check microphone settings, noise levels
2. **STT Accuracy**: Verify Whisper model, audio format
3. **Processing Delays**: Monitor CPU/memory usage
4. **API Failures**: Check network connectivity, rate limits

### Debug Commands
```bash
# Test audio capture
python -m mike_logger.audio_capture --test

# Benchmark STT performance
python -m mike_logger.speech_to_text --benchmark

# Validate API connectivity
python -m mike_logger.task_processor --test-api
```