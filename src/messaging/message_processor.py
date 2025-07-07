#!/usr/bin/env python3
"""
Message Processor for Mike Logger
Processes messages from Telegram, WhatsApp, SMS and integrates with the main system
"""
import os
import json
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

import redis
from anthropic import Anthropic

logger = logging.getLogger(__name__)

class UnifiedMessageProcessor:
    def __init__(self):
        # Initialize Redis connection
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        self.redis_client = redis.from_url(redis_url, decode_responses=True)
        
        # Initialize Anthropic client
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")
        self.anthropic_client = Anthropic(api_key=api_key)
        
        # Setup paths
        self.tasks_dir = Path('/app/data/tasks')
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        
        # Processing settings
        self.processing_interval = int(os.getenv('MESSAGE_PROCESSING_INTERVAL', '5'))
        self.max_retries = int(os.getenv('MESSAGE_MAX_RETRIES', '3'))
        
        self.running = True
        
    def run(self):
        """Main processing loop"""
        logger.info("Starting unified message processor...")
        logger.info(f"Processing interval: {self.processing_interval} seconds")
        logger.info(f"Tasks directory: {self.tasks_dir}")
        
        while self.running:
            try:
                # Process messages from queue
                processed_count = self._process_message_batch()
                
                if processed_count > 0:
                    logger.info(f"Processed {processed_count} messages")
                
                # Sleep before next batch
                time.sleep(self.processing_interval)
                
            except KeyboardInterrupt:
                logger.info("Received shutdown signal")
                self.running = False
                break
            except Exception as e:
                logger.error(f"Error in processing loop: {e}")
                time.sleep(10)  # Wait longer on errors
        
        logger.info("Message processor stopped")
    
    def _process_message_batch(self) -> int:
        """Process a batch of messages from the queue"""
        processed_count = 0
        
        # Process up to 10 messages per batch
        for _ in range(10):
            queue_key = self.redis_client.rpop('message_processing_queue')
            
            if not queue_key:
                break  # No more messages
            
            try:
                if self._process_single_message(queue_key):
                    processed_count += 1
            except Exception as e:
                logger.error(f"Error processing message {queue_key}: {e}")
                self._handle_processing_error(queue_key, str(e))
        
        return processed_count
    
    def _process_single_message(self, queue_key: str) -> bool:
        """Process a single message"""
        try:
            # Get message data from Redis
            message_data = self.redis_client.hgetall(queue_key)
            
            if not message_data:
                logger.warning(f"No data found for queue key: {queue_key}")
                return False
            
            # Parse message
            raw_message = json.loads(message_data['data'])
            
            logger.info(f"Processing {raw_message['source']} message: {raw_message['id']}")
            
            # Update status to processing
            self.redis_client.hset(queue_key, 'status', 'processing')
            
            # Process the message
            processed_task = self._extract_task_from_message(raw_message)
            
            if processed_task:
                # Save to task storage
                task_file = self._save_task(processed_task)
                
                # Update Redis with success
                self.redis_client.hset(queue_key, mapping={
                    'status': 'completed',
                    'completed_at': datetime.now().isoformat(),
                    'task_file': str(task_file)
                })
                
                logger.info(f"Successfully processed message {raw_message['id']} -> {task_file}")
                return True
            else:
                # Mark as failed
                self.redis_client.hset(queue_key, mapping={
                    'status': 'failed',
                    'error': 'Failed to extract task information',
                    'failed_at': datetime.now().isoformat()
                })
                return False
                
        except Exception as e:
            logger.error(f"Error processing message {queue_key}: {e}")
            self._handle_processing_error(queue_key, str(e))
            return False
    
    def _extract_task_from_message(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract structured task information from a message using Claude"""
        try:
            prompt = self._build_extraction_prompt(message)
            
            response = self.anthropic_client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=800,
                temperature=0.1,
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Parse Claude's response
            response_text = response.content[0].text.strip()
            
            # Handle code blocks
            if response_text.startswith('```json'):
                response_text = response_text[7:-3].strip()
            elif response_text.startswith('```'):
                response_text = response_text[3:-3].strip()
            
            extracted_data = json.loads(response_text)
            
            # Create unified task object
            task = {
                'id': message['id'],
                'source': message['source'],
                'source_metadata': message.get('metadata', {}),
                'timestamp': message['timestamp'],
                'raw_input': message['text'],
                'user_id': message.get('user_id', message.get('sender')),
                'processed': {
                    'type': extracted_data.get('type', 'task'),
                    'content': extracted_data.get('content', message['text']),
                    'priority': extracted_data.get('priority', 'medium'),
                    'deadline': extracted_data.get('deadline'),
                    'entities': extracted_data.get('entities', {}),
                    'confidence': extracted_data.get('confidence', 0.8),
                    'actions': extracted_data.get('actions', [])
                },
                'status': 'pending',
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            return task
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude response as JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"Error extracting task from message: {e}")
            return None
    
    def _build_extraction_prompt(self, message: Dict[str, Any]) -> str:
        """Build prompt for task extraction"""
        source_context = {
            'telegram': 'a Telegram message',
            'whatsapp': 'a WhatsApp message', 
            'sms': 'an SMS text message'
        }.get(message['source'], 'a text message')
        
        return f"""Analyze this {source_context} and extract structured task information:

Message: "{message['text']}"
Source: {message['source']}
Message Type: {message.get('type', 'unknown')}
Timestamp: {message['timestamp']}

Extract the following information and return as JSON:

{{
  "type": "task|reminder|idea|question",
  "content": "clear, actionable description",
  "priority": "high|medium|low",
  "deadline": "YYYY-MM-DD or null if no deadline mentioned",
  "entities": {{
    "people": ["names mentioned"],
    "projects": ["project names"],
    "topics": ["main subjects"],
    "locations": ["places mentioned"]
  }},
  "actions": ["specific actions to take"],
  "confidence": 0.0-1.0
}}

Guidelines:
- Focus on actionable content
- Infer priority from language urgency
- Extract deadlines from temporal references
- Set confidence based on clarity of intent
- If the message is vague, mark confidence lower
- For questions, identify what information is needed
- For ideas, focus on the core concept

Return only valid JSON, no explanations."""
    
    def _save_task(self, task: Dict[str, Any]) -> Path:
        """Save task to unified task storage"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        source = task['source']
        task_id = task['id'].replace(':', '_').replace('/', '_')  # Sanitize for filename
        
        filename = f"message_{source}_{timestamp}_{task_id}.json"
        task_file = self.tasks_dir / filename
        
        # Add processing metadata
        task['processing_metadata'] = {
            'processed_by': 'message_processor',
            'processing_version': '1.0',
            'file_path': str(task_file)
        }
        
        with open(task_file, 'w') as f:
            json.dump(task, f, indent=2, ensure_ascii=False)
        
        logger.debug(f"Saved task to: {task_file}")
        return task_file
    
    def _handle_processing_error(self, queue_key: str, error_message: str):
        """Handle processing errors with retry logic"""
        try:
            # Get current retry count
            retry_count = int(self.redis_client.hget(queue_key, 'retry_count') or 0)
            retry_count += 1
            
            if retry_count <= self.max_retries:
                # Retry: put back in queue
                self.redis_client.hset(queue_key, mapping={
                    'status': 'retry',
                    'retry_count': str(retry_count),
                    'last_error': error_message,
                    'retry_at': datetime.now().isoformat()
                })
                
                # Add back to queue with delay
                self.redis_client.lpush('message_processing_queue', queue_key)
                logger.info(f"Queued for retry ({retry_count}/{self.max_retries}): {queue_key}")
            else:
                # Max retries reached
                self.redis_client.hset(queue_key, mapping={
                    'status': 'failed',
                    'retry_count': str(retry_count),
                    'final_error': error_message,
                    'failed_at': datetime.now().isoformat()
                })
                logger.error(f"Max retries reached for {queue_key}: {error_message}")
                
        except Exception as e:
            logger.error(f"Error handling processing error: {e}")
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """Get processing statistics"""
        try:
            # Count messages by status
            all_keys = self.redis_client.keys('message_queue:*')
            
            stats = {
                'total_messages': len(all_keys),
                'by_status': {'pending': 0, 'processing': 0, 'completed': 0, 'failed': 0, 'retry': 0},
                'by_source': {'telegram': 0, 'whatsapp': 0, 'sms': 0},
                'queue_size': self.redis_client.llen('message_processing_queue'),
                'last_updated': datetime.now().isoformat()
            }
            
            for key in all_keys:
                data = self.redis_client.hgetall(key)
                status = data.get('status', 'unknown')
                source = data.get('source', 'unknown')
                
                if status in stats['by_status']:
                    stats['by_status'][status] += 1
                
                if source in stats['by_source']:
                    stats['by_source'][source] += 1
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {'error': str(e)}

def main():
    """Main entry point"""
    logging.basicConfig(
        level=os.getenv('LOG_LEVEL', 'INFO'),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    processor = UnifiedMessageProcessor()
    
    try:
        processor.run()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise

if __name__ == '__main__':
    main()