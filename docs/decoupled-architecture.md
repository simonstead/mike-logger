# Decoupled Architecture Design

## Overview

The Mike Logger system is designed with clear separation between the capture device and processing computer. This allows for:
- **Wearable devices** that focus purely on audio capture
- **Powerful processing** on your laptop or cloud container
- **Flexible deployment** options (local, cloud, hybrid)
- **Scalable architecture** that can grow with your needs

## Three-Layer Architecture

### Layer 1: Capture Device
**Purpose**: Continuous audio capture with minimal processing
**Location**: Wearable device, phone, or dedicated recorder

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            CAPTURE DEVICE                                       │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐      │
│  │ Microphone  │───▶│ Audio Buffer│───▶│ VAD Filter  │───▶│ File Queue  │      │
│  │ (Always On) │    │ (30s chunks)│    │ (Speech     │    │ (.wav files)│      │
│  └─────────────┘    └─────────────┘    │ Detection)  │    └─────────────┘      │
│                                        └─────────────┘           │              │
└────────────────────────────────────────────────────────────────│──────────────┘
```

**Responsibilities:**
- Continuous microphone monitoring
- Audio buffering in 30-second chunks
- Voice Activity Detection (VAD) to filter out silence
- File creation with metadata
- Queue management for upload

### Layer 2: Shared Storage/Queue
**Purpose**: Decoupled communication between capture and processing
**Location**: Cloud storage, network share, or polling endpoint

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           SHARED STORAGE / QUEUE                                │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐      │
│  │ Raw Audio   │───▶│ Processing  │───▶│ Transcripts │───▶│ Final Tasks │      │
│  │ Files       │    │ Queue       │    │ Queue       │    │ Queue       │      │
│  │ (encrypted) │    │ (FIFO)      │    │ (JSON)      │    │ (Structured)│      │
│  └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘      │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**Implementation Options:**
- **File-based**: Dropbox, Google Drive, network share
- **Queue-based**: AWS SQS, Redis, RabbitMQ
- **Database**: PostgreSQL, MongoDB with polling
- **API-based**: Custom REST endpoints

### Layer 3: Processing Computer
**Purpose**: Heavy computational tasks
**Location**: Your laptop, desktop, or cloud container

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         PROCESSING COMPUTER                                     │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐      │
│  │ File Poller │───▶│ Whisper STT │───▶│ Claude API  │───▶│ Task System │      │
│  │ (every 30s) │    │ (Local)     │    │ (Extraction)│    │ (Storage)   │      │
│  └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘      │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**Responsibilities:**
- Monitor shared storage for new audio files
- Run Whisper STT locally (GPU accelerated)
- Extract tasks using Claude API
- Store results in task management system
- Clean up processed files

## Data Models

### Input: Audio Segments
```json
{
  "filename": "segment_20240107_143022.wav",
  "duration": 30.0,
  "sample_rate": 16000,
  "channels": 1,
  "format": "WAV/PCM",
  "metadata": {
    "timestamp": "2024-01-07T14:30:22.000Z",
    "device_id": "mike-logger-001",
    "location": "office",
    "encryption_key": "base64-encoded-key",
    "vad_confidence": 0.89
  }
}
```

### Processing Queue Status
```json
{
  "id": "uuid-1",
  "audio_file": "segment_20240107_143022.wav",
  "status": "pending",
  "priority": 7,
  "created_at": "2024-01-07T14:30:22.000Z",
  "started_at": null,
  "completed_at": null,
  "retry_count": 0,
  "error_message": null
}
```

Status values:
- `pending`: Waiting to be processed
- `processing`: Currently being transcribed
- `completed`: Successfully processed
- `failed`: Error occurred, may retry
- `expired`: Too old, skipped

Priority levels:
- `1-3`: Low priority (mostly silence)
- `4-6`: Medium priority (some speech)
- `7-10`: High priority (clear speech detected)

### Transcript Output
```json
{
  "id": "uuid-4",
  "source_file": "segment_20240107_143022.wav",
  "timestamp": "2024-01-07T14:30:22.000Z",
  "duration": 30.0,
  "language": "en",
  "confidence": 0.89,
  "text": "Hey, remind me to call Sarah about the project meeting tomorrow at 3pm",
  "segments": [
    {
      "start": 0.0,
      "end": 5.2,
      "text": "Hey, remind me to call Sarah",
      "confidence": 0.92,
      "speaker": "user"
    },
    {
      "start": 5.2,
      "end": 10.8,
      "text": "about the project meeting tomorrow at 3pm",
      "confidence": 0.86,
      "speaker": "user"
    }
  ],
  "processing_stats": {
    "whisper_model": "base",
    "processing_time": 2.3,
    "gpu_used": true
  }
}
```

### Extracted Tasks
```json
{
  "id": "uuid-5",
  "source_transcript": "uuid-4",
  "extracted_at": "2024-01-07T14:30:35.000Z",
  "tasks": [
    {
      "id": "task-1",
      "type": "reminder",
      "content": "Call Sarah about project meeting",
      "priority": "high",
      "deadline": "2024-01-08T15:00:00.000Z",
      "status": "pending",
      "confidence": 0.95,
      "entities": {
        "person": "Sarah",
        "action": "call",
        "topic": "project meeting",
        "datetime": "tomorrow at 3pm"
      },
      "tags": ["work", "meeting", "urgent"]
    }
  ],
  "ideas": [
    {
      "id": "idea-1",
      "content": "Consider using video calls for better engagement",
      "category": "improvement",
      "confidence": 0.72
    }
  ],
  "questions": [
    {
      "id": "question-1",
      "content": "What's the agenda for the project meeting?",
      "urgency": "medium",
      "confidence": 0.88
    }
  ]
}
```

## Communication Patterns

### 1. File-Based Communication
**Best for**: Simple setups, development, low-tech solutions

```python
# Capture device writes files to shared folder
def save_audio_segment(audio_data, timestamp):
    filename = f"audio_queue/segment_{timestamp}.wav"
    save_wav_file(filename, audio_data)
    
    # Write metadata
    metadata = {
        "timestamp": timestamp,
        "device_id": get_device_id(),
        "vad_confidence": calculate_vad_confidence(audio_data)
    }
    with open(f"{filename}.meta", "w") as f:
        json.dump(metadata, f)

# Processing computer polls for new files
def poll_for_new_files():
    for file in os.listdir("audio_queue"):
        if file.endswith(".wav") and os.path.exists(f"{file}.meta"):
            process_audio_file(file)
```

### 2. Queue-Based Communication
**Best for**: Reliable delivery, error handling, scaling

```python
# Using AWS SQS example
import boto3

# Capture device sends messages
def queue_audio_file(filename, metadata):
    sqs = boto3.client('sqs')
    message = {
        'filename': filename,
        'metadata': metadata,
        'priority': calculate_priority(metadata)
    }
    sqs.send_message(
        QueueUrl='https://sqs.region.amazonaws.com/account/audio-queue',
        MessageBody=json.dumps(message)
    )

# Processing computer receives messages
def process_queue():
    sqs = boto3.client('sqs')
    messages = sqs.receive_message(
        QueueUrl='https://sqs.region.amazonaws.com/account/audio-queue',
        MaxNumberOfMessages=10
    )
    
    for message in messages.get('Messages', []):
        process_audio_message(message)
        sqs.delete_message(
            QueueUrl='https://sqs.region.amazonaws.com/account/audio-queue',
            ReceiptHandle=message['ReceiptHandle']
        )
```

### 3. API-Based Communication
**Best for**: Real-time processing, custom logic, monitoring

```python
# Capture device posts to API
def upload_audio_segment(audio_data, metadata):
    files = {'audio': audio_data}
    data = {'metadata': json.dumps(metadata)}
    
    response = requests.post(
        'https://your-api.com/upload',
        files=files,
        data=data,
        headers={'Authorization': f'Bearer {get_auth_token()}'}
    )
    
    return response.json()

# Processing computer provides API
@app.route('/upload', methods=['POST'])
def upload_audio():
    audio_file = request.files['audio']
    metadata = json.loads(request.form['metadata'])
    
    # Queue for processing
    processing_queue.put({
        'audio_file': audio_file,
        'metadata': metadata,
        'uploaded_at': datetime.now()
    })
    
    return {'status': 'queued', 'id': str(uuid.uuid4())}
```

## Deployment Scenarios

### Scenario 1: Local Development
- **Capture**: Python script on laptop
- **Storage**: Local filesystem
- **Processing**: Same laptop

### Scenario 2: Wearable + Laptop
- **Capture**: ESP32 or phone app
- **Storage**: Dropbox or Google Drive
- **Processing**: Your laptop polling cloud storage

### Scenario 3: Wearable + Cloud
- **Capture**: Dedicated device
- **Storage**: AWS S3 + SQS
- **Processing**: AWS Lambda or ECS container

### Scenario 4: Hybrid Security
- **Capture**: Encrypted device
- **Storage**: Your own VPS
- **Processing**: Local + cloud (Claude API only)

## Implementation Recommendations

### Start Simple: File-Based
1. Use shared folder (Dropbox, Google Drive)
2. Capture device writes .wav files
3. Processing computer polls every 30 seconds
4. Clean up processed files

### Scale Up: Queue-Based
1. Add Redis or AWS SQS for reliability
2. Implement retry logic and dead letter queues
3. Add monitoring and alerting
4. Scale processing horizontally

### Production: API-Based
1. Custom API with authentication
2. Real-time WebSocket connections
3. Advanced error handling
4. Comprehensive logging and metrics

## Security Considerations

### Data in Transit
- **File-based**: Encrypt files before upload
- **Queue-based**: Use TLS and message encryption
- **API-based**: HTTPS with certificate pinning

### Data at Rest
- **Local encryption**: AES-256 with device-specific keys
- **Cloud storage**: Server-side encryption
- **Database**: Encrypted columns for sensitive data

### Access Control
- **Authentication**: Device certificates or API keys
- **Authorization**: Per-device permissions
- **Audit logging**: Track all access and changes

This decoupled architecture provides flexibility while maintaining security and reliability for your always-on voice assistant system.