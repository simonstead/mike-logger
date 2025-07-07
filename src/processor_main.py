#!/usr/bin/env python3
"""
Mike Logger - Audio Processing Service
Runs in Docker container, processes audio files from shared volume
"""
import os
import time
import json
import logging
import signal
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

import whisper
from anthropic import Anthropic
import redis
from prometheus_client import start_http_server, Counter, Histogram, Gauge

# Configure logging
logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Metrics
PROCESSED_FILES = Counter('mike_logger_files_processed_total', 'Total audio files processed')
PROCESSING_TIME = Histogram('mike_logger_processing_seconds', 'Time spent processing files')
TRANSCRIPTION_TIME = Histogram('mike_logger_transcription_seconds', 'Time spent on transcription')
TASK_EXTRACTION_TIME = Histogram('mike_logger_task_extraction_seconds', 'Time spent extracting tasks')
QUEUE_SIZE = Gauge('mike_logger_queue_size', 'Number of files in processing queue')
ERRORS = Counter('mike_logger_errors_total', 'Total processing errors', ['error_type'])

class AudioProcessor:
    def __init__(self):
        self.whisper_model = None
        self.anthropic_client = None
        self.redis_client = None
        self.running = True
        
        # Configuration
        self.whisper_model_name = os.getenv('WHISPER_MODEL', 'base')
        self.processing_interval = int(os.getenv('PROCESSING_INTERVAL', '30'))
        self.audio_dir = Path('/app/data/audio')
        self.transcripts_dir = Path('/app/data/transcripts')
        self.tasks_dir = Path('/app/data/tasks')
        
        # Ensure directories exist
        for dir_path in [self.audio_dir, self.transcripts_dir, self.tasks_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
        
        self.setup_signal_handlers()
        
    def setup_signal_handlers(self):
        """Setup graceful shutdown handlers"""
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)
        
    def shutdown(self, signum, frame):
        """Graceful shutdown"""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False
        
    def initialize(self):
        """Initialize all services"""
        logger.info("Initializing Mike Logger Processor...")
        
        # Initialize Whisper
        logger.info(f"Loading Whisper model: {self.whisper_model_name}")
        try:
            # Try to load model with retry logic for download issues
            for attempt in range(3):
                try:
                    self.whisper_model = whisper.load_model(self.whisper_model_name)
                    logger.info("Whisper model loaded successfully")
                    break
                except Exception as e:
                    if attempt < 2:
                        logger.warning(f"Attempt {attempt + 1} failed to load Whisper model: {e}")
                        logger.info("Retrying in 10 seconds...")
                        time.sleep(10)
                    else:
                        raise e
        except Exception as e:
            logger.error(f"Failed to load Whisper model after 3 attempts: {e}")
            ERRORS.labels(error_type='whisper_init').inc()
            raise
            
        # Initialize Anthropic client
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            logger.error("ANTHROPIC_API_KEY not set")
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")
            
        try:
            self.anthropic_client = Anthropic(api_key=api_key)
            logger.info("Anthropic client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Anthropic client: {e}")
            ERRORS.labels(error_type='anthropic_init').inc()
            raise
            
        # Initialize Redis (optional)
        try:
            redis_url = os.getenv('REDIS_URL', 'redis://redis:6379')
            self.redis_client = redis.from_url(redis_url, decode_responses=True)
            self.redis_client.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.warning(f"Redis not available: {e}")
            self.redis_client = None
            
        # Start metrics server
        metrics_port = int(os.getenv('METRICS_PORT', '8000'))
        start_http_server(metrics_port)
        logger.info(f"Metrics server started on port {metrics_port}")
        
    def get_pending_files(self):
        """Get list of audio files to process"""
        audio_files = list(self.audio_dir.glob('*.wav'))
        
        # Sort by creation time (oldest first)
        audio_files.sort(key=lambda f: f.stat().st_mtime)
        
        QUEUE_SIZE.set(len(audio_files))
        return audio_files
        
    def process_audio_file(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Process a single audio file through the complete pipeline"""
        logger.info(f"Processing audio file: {file_path.name}")
        
        with PROCESSING_TIME.time():
            try:
                # Step 1: Transcribe audio
                transcript = self.transcribe_audio(file_path)
                if not transcript:
                    logger.warning(f"No transcript generated for {file_path.name}")
                    return None
                    
                # Step 2: Save transcript
                transcript_file = self.save_transcript(transcript, file_path)
                
                # Step 3: Extract tasks
                tasks = self.extract_tasks(transcript)
                
                # Step 4: Save tasks
                if tasks:
                    task_file = self.save_tasks(tasks, transcript_file)
                    logger.info(f"Extracted {len(tasks)} tasks from {file_path.name}")
                else:
                    task_file = None
                    logger.info(f"No tasks extracted from {file_path.name}")
                
                # Step 5: Cleanup
                self.cleanup_audio_file(file_path)
                
                PROCESSED_FILES.inc()
                
                result = {
                    'audio_file': str(file_path),
                    'transcript_file': str(transcript_file),
                    'task_file': str(task_file) if task_file else None,
                    'transcript_text': transcript['text'],
                    'task_count': len(tasks) if tasks else 0,
                    'processed_at': datetime.now().isoformat()
                }
                
                # Update Redis if available
                if self.redis_client:
                    self.update_redis_status(file_path.name, 'completed', result)
                
                return result
                
            except Exception as e:
                logger.error(f"Error processing {file_path.name}: {e}")
                ERRORS.labels(error_type='processing').inc()
                
                if self.redis_client:
                    self.update_redis_status(file_path.name, 'failed', {'error': str(e)})
                
                return None
                
    def transcribe_audio(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Transcribe audio file using Whisper"""
        with TRANSCRIPTION_TIME.time():
            try:
                logger.debug(f"Transcribing {file_path.name} with Whisper")
                
                result = self.whisper_model.transcribe(
                    str(file_path),
                    language=os.getenv('WHISPER_LANGUAGE', 'en'),
                    task='transcribe',
                    temperature=0.0
                )
                
                # Add metadata
                result['file_path'] = str(file_path)
                result['file_size'] = file_path.stat().st_size
                result['processed_at'] = datetime.now().isoformat()
                result['model'] = self.whisper_model_name
                
                logger.debug(f"Transcription completed: {len(result['text'])} characters")
                return result
                
            except Exception as e:
                logger.error(f"Transcription failed for {file_path.name}: {e}")
                ERRORS.labels(error_type='transcription').inc()
                return None
                
    def save_transcript(self, transcript: Dict[str, Any], audio_file: Path) -> Path:
        """Save transcript to JSON file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        transcript_file = self.transcripts_dir / f"transcript_{timestamp}_{audio_file.stem}.json"
        
        with open(transcript_file, 'w') as f:
            json.dump(transcript, f, indent=2, ensure_ascii=False)
            
        logger.debug(f"Transcript saved: {transcript_file.name}")
        return transcript_file
        
    def extract_tasks(self, transcript: Dict[str, Any]) -> Optional[list]:
        """Extract tasks from transcript using Claude"""
        text = transcript.get('text', '').strip()
        
        if len(text) < 10:  # Skip very short transcripts
            logger.debug("Transcript too short for task extraction")
            return None
            
        with TASK_EXTRACTION_TIME.time():
            try:
                prompt = self.build_task_extraction_prompt(text)
                
                response = self.anthropic_client.messages.create(
                    model="claude-3-haiku-20240307",  # Fast model for task extraction
                    max_tokens=1000,
                    temperature=0.1,
                    messages=[{"role": "user", "content": prompt}]
                )
                
                # Parse JSON response
                response_text = response.content[0].text.strip()
                
                # Handle code blocks
                if response_text.startswith('```json'):
                    response_text = response_text[7:-3].strip()
                elif response_text.startswith('```'):
                    response_text = response_text[3:-3].strip()
                    
                tasks = json.loads(response_text)
                
                # Validate tasks format
                if isinstance(tasks, list):
                    return tasks
                elif isinstance(tasks, dict) and 'tasks' in tasks:
                    return tasks['tasks']
                else:
                    logger.warning(f"Unexpected task format: {type(tasks)}")
                    return None
                    
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse tasks JSON: {e}")
                ERRORS.labels(error_type='task_parsing').inc()
                return None
            except Exception as e:
                logger.error(f"Task extraction failed: {e}")
                ERRORS.labels(error_type='task_extraction').inc()
                return None
                
    def build_task_extraction_prompt(self, text: str) -> str:
        """Build prompt for task extraction"""
        return f"""Analyze this conversation transcript and extract actionable items:

"{text}"

Please identify and return a JSON array of objects with this structure:
[
  {{
    "type": "task|reminder|idea|question",
    "content": "description of the item",
    "priority": "high|medium|low",
    "deadline": "YYYY-MM-DD or null",
    "confidence": 0.0-1.0,
    "entities": {{
      "person": "name if mentioned",
      "action": "verb describing what to do",
      "topic": "subject matter"
    }}
  }}
]

Rules:
- Only extract items that are actionable or noteworthy
- Set realistic priorities based on language used
- Extract deadlines from temporal references ("tomorrow", "next week", etc.)
- Include confidence score based on clarity
- Return empty array [] if no actionable items found
- Return only valid JSON, no explanations

Focus on:
- Direct requests or reminders
- Action items mentioned
- Questions that need answers
- Important ideas to remember

Skip:
- Casual conversation
- Greetings
- Filler words"""

    def save_tasks(self, tasks: list, transcript_file: Path) -> Path:
        """Save extracted tasks to JSON file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        task_file = self.tasks_dir / f"tasks_{timestamp}_{transcript_file.stem}.json"
        
        task_data = {
            'source_transcript': str(transcript_file),
            'extracted_at': datetime.now().isoformat(),
            'task_count': len(tasks),
            'tasks': tasks
        }
        
        with open(task_file, 'w') as f:
            json.dump(task_data, f, indent=2, ensure_ascii=False)
            
        logger.debug(f"Tasks saved: {task_file.name}")
        return task_file
        
    def cleanup_audio_file(self, file_path: Path):
        """Remove processed audio file"""
        try:
            keep_audio = os.getenv('KEEP_AUDIO_FILES', 'false').lower() == 'true'
            if not keep_audio:
                file_path.unlink()
                logger.debug(f"Cleaned up audio file: {file_path.name}")
        except Exception as e:
            logger.warning(f"Failed to cleanup {file_path.name}: {e}")
            
    def update_redis_status(self, filename: str, status: str, data: Dict[str, Any]):
        """Update processing status in Redis"""
        try:
            key = f"processing:{filename}"
            self.redis_client.hset(key, mapping={
                'status': status,
                'updated_at': datetime.now().isoformat(),
                'data': json.dumps(data)
            })
            self.redis_client.expire(key, 86400)  # Expire after 24 hours
        except Exception as e:
            logger.warning(f"Failed to update Redis status: {e}")
            
    def run(self):
        """Main processing loop"""
        logger.info("Starting audio processing loop...")
        
        while self.running:
            try:
                # Get pending files
                pending_files = self.get_pending_files()
                
                if pending_files:
                    logger.info(f"Found {len(pending_files)} files to process")
                    
                    for file_path in pending_files:
                        if not self.running:
                            break
                            
                        # Update Redis status
                        if self.redis_client:
                            self.update_redis_status(file_path.name, 'processing', {})
                            
                        # Process file
                        result = self.process_audio_file(file_path)
                        
                        if result:
                            logger.info(f"Successfully processed {file_path.name}")
                        else:
                            logger.warning(f"Failed to process {file_path.name}")
                            
                else:
                    logger.debug("No files to process")
                    
                # Wait before next check
                time.sleep(self.processing_interval)
                
            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt")
                break
            except Exception as e:
                logger.error(f"Unexpected error in processing loop: {e}")
                ERRORS.labels(error_type='loop').inc()
                time.sleep(60)  # Wait longer on unexpected errors
                
        logger.info("Processing loop stopped")

def main():
    """Main entry point"""
    processor = AudioProcessor()
    
    try:
        processor.initialize()
        processor.run()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
    finally:
        logger.info("Mike Logger Processor stopped")

if __name__ == '__main__':
    main()