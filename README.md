# Mike Logger - Always-On Voice Assistant

An experimental system for continuous voice capture, speech-to-text processing, and intelligent task extraction using private infrastructure.

## Overview

This project implements an "always on" microphone system that:
- Continuously captures audio throughout the day
- Converts speech to text using private, self-hosted models
- Processes conversations to extract tasks, ideas, and action items
- Integrates with AI agents (Claude) to organize and act on information

## Architecture Options

### 1. Minimal Prototype Architecture

**Hardware Requirements:**
- Raspberry Pi 4B (2GB+ RAM) + USB microphone
- OR existing computer with built-in microphone
- 32GB+ storage for audio buffering

**Software Stack:**
- **Audio Capture**: Python with `pyaudio` for continuous recording
- **Speech-to-Text**: OpenAI Whisper running locally
- **Processing**: Python scripts polling for new transcripts
- **Task Agent**: Claude API integration for task extraction

**Data Flow:**
```
Microphone → Audio Buffer → Whisper STT → Text Queue → Processing Script → Claude API → Task Updates
```

### 2. Secure Production Architecture

**Infrastructure:**
- Self-hosted server (VPS or on-premises)
- End-to-end encryption for all data
- Voice Activity Detection (VAD) for efficiency

**Components:**
1. **Edge Device**: Wearable device with VAD → encrypted audio chunks
2. **Private Server**: Whisper processing + secure API
3. **Local Agent**: Polls server, executes tasks locally
4. **Storage**: Encrypted database with retention policies

**Security Features:**
- Zero-knowledge architecture
- Automatic data deletion after processing
- VPN/Wireguard tunnel for all communication
- Device-specific encryption keys

## Speech-to-Text Solutions

### Recommended: OpenAI Whisper (Open Source)
- **License**: MIT License - completely free for commercial use
- **Models**: tiny, base, small, medium, large, large-v3
- **Recommendation**: `base` for quality/speed balance, `tiny` for real-time
- **Benefits**: Fully offline, excellent accuracy, GPU optional, no API costs
- **Installation**: `pip install git+https://github.com/openai/whisper.git`
- **System Requirements**: 4GB+ RAM, 10GB+ for larger models

### Cost Comparison:
- **Local Whisper**: Hardware costs only ($0 per minute)
- **OpenAI STT API**: $0.006 per minute
- **For 8 hours daily**: ~$1,050/year API vs one-time hardware cost

### Alternatives:
- **Wav2Vec2**: Facebook's model, good for real-time
- **SpeechRecognition**: Multiple backend options

## Hardware Options

### Minimal Setup:
- Raspberry Pi 4B or existing computer
- USB microphone or 3.5mm lapel mic
- Power bank for mobility

### Wearable Options:
- ESP32 with I2S microphone module
- Smartphone with background recording app
- Dedicated voice recorder with WiFi

### Production Setup:
- Intel NUC or mini-PC for processing
- High-quality omnidirectional microphone
- Dedicated storage server

## Data Processing Pipeline

### Stage 1: Audio Processing
- Voice Activity Detection (VAD)
- Noise reduction and normalization
- Audio chunking (5-minute segments)

### Stage 2: Text Conversion
- Whisper STT processing
- Speaker diarization (if needed)
- Timestamp preservation

### Stage 3: Intelligence Layer
- NLP for task/idea extraction
- Context window management
- Priority scoring

### Stage 4: Action & Integration
- Claude API for task planning
- Local file system updates
- Notification system

## Implementation Phases

### Phase 1: Minimal Prototype (1-2 days)
1. Test Whisper with sample recordings
2. Build text file processing script
3. Integrate Claude API
4. Add continuous audio capture

### Phase 2: Secure Version (1-2 weeks)
1. Implement encryption layer
2. Add VAD for efficiency
3. Deploy Docker containers
4. Set up secure API endpoints

## Key Design Decisions

### Privacy & Security
- All processing happens on owned infrastructure
- No cloud dependencies for core functionality
- Encrypted storage and transmission
- Automatic data expiration

### Processing Tradeoffs
| Approach | Pros | Cons |
|----------|------|------|
| Local Processing | Maximum privacy, no latency | Limited by hardware |
| Private Server | More power, centralized | Requires secure transmission |
| Hybrid | Best of both worlds | More complex |

### Audio Quality vs Battery Life
- High quality (48kHz): Better accuracy, 4-6 hour battery
- Optimized (16kHz + VAD): 12-24 hour battery, may miss quiet speech

## Cost Estimates

- **Minimal Prototype**: $0 (using existing hardware)
- **Raspberry Pi Setup**: ~$100-150
- **Private Server**: $20-50/month VPS
- **Wearable Device**: $50-200 depending on approach

## Quick Start

```bash
# Install dependencies
pip install whisper pyaudio anthropic cryptography webrtcvad

# Clone repository
git clone [repository-url]
cd mike_logger

# Run minimal prototype
python main.py --mode minimal
```

## Project Structure

```
mike_logger/
├── src/
│   ├── audio_capture.py    # Continuous recording
│   ├── speech_to_text.py   # Whisper integration
│   ├── task_processor.py   # Claude API & NLP
│   └── main.py            # Orchestration
├── config/
│   ├── settings.json      # Configuration
│   └── prompts.json       # AI prompts
├── data/
│   ├── audio/            # Temporary audio files
│   ├── transcripts/      # Processed text
│   └── tasks/           # Extracted tasks
└── docs/
    └── architecture.md   # Detailed architecture
```

## Next Steps

1. Choose between minimal prototype or secure architecture
2. Set up Whisper on your processing device
3. Configure Claude API access
4. Start with "one-shot" voice notes before continuous capture
5. Iterate based on real-world usage

## Privacy Considerations

- Audio is processed locally or on your own server
- No third-party cloud services for audio/transcription
- Implement data retention policies
- Consider legal requirements for recording in your jurisdiction

## Contributing

This is an experimental project. Feel free to fork and adapt for your needs.

## License

[Choose appropriate license]