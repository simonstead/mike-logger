# Quick Start Guide

Get Mike Logger running in 5 minutes!

## Prerequisites

- Docker Desktop installed and running
- Python 3.8+ (for audio capture on Mac)
- Microphone access permissions

## 1. Clone and Setup

```bash
git clone https://github.com/simonstead/mike-logger.git
cd mike-logger

# Install host dependencies for audio capture
pip3 install pyaudio numpy webrtcvad soundfile

# Configure environment
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

## 2. Start Services

```bash
# Build and start all Docker services
docker-compose up --build -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f processor
```

## 3. Start Audio Capture

In a separate terminal:

```bash
# Start native audio capture (runs on Mac host)
python3 host_audio_capture.py
```

## 4. Monitor System

- **Dashboard**: http://localhost:8080
- **Metrics**: http://localhost:9090  
- **Logs**: `docker-compose logs -f`

## 5. Test the System

1. Say something like: "Remind me to call Sarah about the project meeting tomorrow"
2. Watch the logs: `docker-compose logs -f processor`
3. Check the dashboard: http://localhost:8080
4. Look for files in:
   - `data/audio/` - Raw audio segments
   - `data/transcripts/` - Whisper transcriptions  
   - `data/tasks/` - Extracted tasks from Claude

## Troubleshooting

**Audio not working:**
```bash
# List audio devices
python3 -c "import pyaudio; p = pyaudio.PyAudio(); [print(f'{i}: {p.get_device_info_by_index(i)[\"name\"]}') for i in range(p.get_device_count()) if p.get_device_info_by_index(i)['maxInputChannels'] > 0]"

# Use specific device
AUDIO_DEVICE_INDEX=1 python3 host_audio_capture.py
```

**Docker issues:**
```bash
# Rebuild containers
docker-compose down
docker-compose up --build

# Check logs
docker-compose logs processor
```

**API issues:**
- Verify ANTHROPIC_API_KEY in .env
- Check Claude API quota/billing

## Commands

```bash
# Start everything
make up

# Stop everything  
make down

# View logs
make logs

# Get shell in processor
make shell

# Show status
make status
```

That's it! You now have a working always-on voice assistant.