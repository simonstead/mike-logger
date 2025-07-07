# Docker Deployment on macOS

## Why Docker for Mike Logger?

Using Docker on your Mac provides several key benefits:

1. **Cross-platform consistency** - Same environment across Mac, Linux, Windows
2. **Isolated dependencies** - No conflicts with your system Python/libraries
3. **Easy scaling** - Add more processing containers as needed
4. **Clean separation** - Audio capture vs processing concerns
5. **Production-ready** - Same containers work in cloud deployment

## Architecture Overview

Since Docker containers on Mac cannot directly access the microphone, we use a **hybrid architecture**:

```
┌─────────────────────────────────────────────────────────────────┐
│                        macOS HOST                               │
│                                                                 │
│  ┌─────────────────┐              ┌─────────────────┐           │
│  │ Audio Capture   │──────────────│ Shared Volume   │           │
│  │ (Native Python) │  .wav files  │ ./data/audio/   │           │
│  └─────────────────┘              └─────────────────┘           │
└─────────────────────────────────────────┼───────────────────────┘
                                          │
┌─────────────────────────────────────────┼───────────────────────┐
│                   DOCKER                │                       │
│                                         │                       │
│  ┌─────────────────┐    ┌─────────────────┐    ┌──────────────┐ │
│  │ Whisper STT     │────│ Claude API      │────│ Task Storage │ │
│  │ Container       │    │ Processor       │    │ Container    │ │
│  └─────────────────┘    └─────────────────┘    └──────────────┘ │
│                                         │                       │
│  ┌─────────────────┐    ┌─────────────────┐    ┌──────────────┐ │
│  │ Redis Queue     │────│ Web Dashboard   │────│ Monitoring   │ │
│  │ Container       │    │ Container       │    │ (Optional)   │ │
│  └─────────────────┘    └─────────────────┘    └──────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## Key Components

### Host-side (macOS)
- **Audio Capture Script**: Native Python script that accesses microphone
- **Shared Volumes**: Directories mounted into Docker containers
- **File Coordination**: Manages audio file lifecycle

### Docker-side (Containers)
- **Processor Container**: Runs Whisper STT and Claude API calls
- **Redis Container**: Job queue and state management
- **Dashboard Container**: Web interface for monitoring
- **Prometheus Container**: Metrics and monitoring (optional)

## File Structure

```
mike_logger/
├── docker-compose.yml          # Main orchestration file
├── Dockerfile.processor        # Whisper + Claude processing
├── Dockerfile.dashboard        # Web monitoring interface
├── requirements.txt            # Python dependencies
├── requirements-dashboard.txt  # Dashboard dependencies
├── host_audio_capture.py      # Native Mac audio capture
├── .env                       # Environment configuration
├── data/                      # Shared volumes
│   ├── audio/                 # Raw audio files
│   ├── transcripts/           # Processed text
│   └── tasks/                 # Extracted tasks
├── logs/                      # Container logs
└── config/                    # Configuration files
```

## Communication Flow

1. **Audio Capture** (Mac host):
   ```python
   # Continuously records audio
   microphone → pyaudio → VAD → segment.wav → ./data/audio/
   ```

2. **Processing Trigger** (Docker):
   ```python
   # Watches for new files
   ./data/audio/*.wav → Whisper STT → Claude API → ./data/tasks/
   ```

3. **File Cleanup** (Automated):
   ```python
   # Removes processed files
   processed_audio → delete (configurable retention)
   ```

## Docker Compose Services

### Core Services

#### `processor`
- **Purpose**: Main processing engine
- **Technology**: Python + Whisper + Claude API
- **Resources**: 2-4GB RAM, 2 CPU cores
- **Volumes**: Audio input, transcript/task output
- **Health Check**: Endpoint monitoring

#### `redis`
- **Purpose**: Job queue and state management
- **Technology**: Redis 7 with persistence
- **Resources**: 512MB RAM
- **Persistence**: Append-only file for durability
- **Port**: 6379 (internal only)

### Optional Services

#### `dashboard`
- **Purpose**: Web interface for monitoring
- **Technology**: Flask + Gunicorn
- **Port**: http://localhost:8080
- **Features**: File browser, processing stats, logs

#### `prometheus`
- **Purpose**: Metrics collection
- **Technology**: Prometheus
- **Port**: http://localhost:9090
- **Metrics**: Processing time, success rate, queue depth

## Quick Start Commands

```bash
# Initial setup
git clone <repo>
cd mike_logger
cp .env.example .env
# Edit .env with your Claude API key

# Start core services
docker-compose up -d processor redis

# Start audio capture (in separate terminal)
python3 host_audio_capture.py

# Monitor processing
docker-compose logs -f processor

# Optional: Start dashboard
docker-compose up -d dashboard
open http://localhost:8080
```

## Configuration Options

### Environment Variables (.env)
```bash
# Required
ANTHROPIC_API_KEY=your_key_here

# Whisper settings
WHISPER_MODEL=base              # tiny, base, small, medium, large
WHISPER_LANGUAGE=en

# Processing
PROCESSING_INTERVAL=30          # seconds between file checks
LOG_LEVEL=INFO                  # DEBUG, INFO, WARNING, ERROR

# Resources
MEMORY_LIMIT=4G                 # Container memory limit
CPU_LIMIT=2                     # Container CPU limit

# Optional features
ENABLE_DASHBOARD=true
ENABLE_METRICS=false
```

### Volume Mounts
```yaml
volumes:
  # Audio exchange
  - ./data/audio:/app/data/audio

  # Output storage
  - ./data/transcripts:/app/data/transcripts
  - ./data/tasks:/app/data/tasks

  # Logs and debugging
  - ./logs:/app/logs

  # Model caching (avoid re-downloads)
  - whisper-cache:/root/.cache/whisper
```

## Development Workflow

### Making Changes
```bash
# Edit code in src/
vim src/processor_main.py

# Rebuild and restart
docker-compose build processor
docker-compose up -d processor

# View logs
docker-compose logs -f processor
```

### Debugging
```bash
# Enter running container
docker-compose exec processor bash

# Check processing status
docker-compose exec redis redis-cli KEYS "*"

# Manual file processing
docker-compose exec processor python -c "
from src.processor import process_file
process_file('data/audio/test.wav')
"
```

### Testing
```bash
# Test audio capture
python3 -c "
from host_audio_capture import HostAudioCapture
import time
capture = HostAudioCapture()
# Record for 10 seconds
import threading
t = threading.Thread(target=capture.start_capture)
t.start()
time.sleep(10)
"

# Test processing pipeline
echo "Test audio file" > data/audio/test.wav
docker-compose logs -f processor
```

## Production Considerations

### Security
- Use Docker secrets for API keys
- Network isolation between containers
- Read-only filesystem where possible
- Non-root user inside containers

### Scaling
```yaml
# Scale processing workers
docker-compose up -d --scale processor=3

# Use external Redis for multi-host
REDIS_URL=redis://your-redis-cluster:6379
```

### Monitoring
- Prometheus metrics collection
- Grafana dashboards
- Log aggregation (ELK stack)
- Health check endpoints

### Resource Management
```yaml
deploy:
  resources:
    limits:
      memory: 4G
      cpus: '2.0'
    reservations:
      memory: 2G
      cpus: '1.0'
```

## Troubleshooting

### Common Issues

**Audio not being captured:**
```bash
# Check Python audio dependencies
pip3 list | grep -E "(pyaudio|soundfile)"

# Test microphone access
python3 -c "import pyaudio; p = pyaudio.PyAudio(); print(p.get_device_count())"
```

**Docker containers not starting:**
```bash
# Check Docker Desktop is running
docker info

# Check logs
docker-compose logs processor

# Check disk space
df -h
```

**Processing not working:**
```bash
# Check API key
docker-compose exec processor python -c "
import os; print('API Key:', os.getenv('ANTHROPIC_API_KEY')[:10] + '...')
"

# Check Whisper model
docker-compose exec processor python -c "
import whisper; model = whisper.load_model('base'); print('Model loaded')
"
```

**Performance issues:**
```bash
# Monitor resource usage
docker stats

# Check processing queue
docker-compose exec redis redis-cli LLEN processing_queue

# Analyze bottlenecks
docker-compose exec processor python -c "
import psutil
print(f'CPU: {psutil.cpu_percent()}%')
print(f'Memory: {psutil.virtual_memory().percent}%')
"
```

## Migration from Native Setup

If you have an existing native Python setup:

1. **Export existing data:**
   ```bash
   # Backup existing data
   cp -r data/ data_backup/
   ```

2. **Install Docker version:**
   ```bash
   # Follow Docker setup steps
   docker-compose up -d processor redis
   ```

3. **Migrate configuration:**
   ```bash
   # Copy settings to .env
   cp config/settings.py .env.new
   # Edit .env.new and rename to .env
   ```

4. **Test compatibility:**
   ```bash
   # Process existing audio files
   cp data_backup/audio/* data/audio/
   docker-compose logs -f processor
   ```

This Docker approach provides the best of both worlds: native performance for audio capture and containerized consistency for processing.