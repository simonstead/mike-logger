# Messaging Integration for Mike Logger

## Overview

This document outlines how to integrate Telegram, WhatsApp, and SMS messaging platforms with Mike Logger to allow task submission via text messages. This creates a multi-modal input system where tasks can come from:
- 🎤 Voice (primary - always-on microphone)
- 💬 Text messages (secondary - quick thoughts on the go)
- 🎯 Direct API calls (tertiary - from other apps)

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         INPUT SOURCES                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌──────────┐ │
│  │   Voice     │    │  Telegram   │    │  WhatsApp   │    │   SMS    │ │
│  │  (Primary)  │    │    Bot      │    │  Business   │    │  (Twilio)│ │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘    └─────┬────┘ │
│         │                   │                   │                 │      │
└─────────┼───────────────────┼───────────────────┼─────────────────┼──────┘
          │                   │                   │                 │
          ▼                   ▼                   ▼                 ▼
    ┌─────────────┐    ┌─────────────────────────────────────────────┐
    │ Audio Files │    │         Message Queue (Redis/SQS)            │
    │   (.wav)    │    │    - telegram:task:uuid                     │
    └──────┬──────┘    │    - whatsapp:task:uuid                     │
           │           │    - sms:task:uuid                          │
           │           └──────────────────┬──────────────────────────┘
           │                              │
           ▼                              ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │                    PROCESSING PIPELINE                          │
    │  ┌─────────────┐         ┌─────────────┐    ┌─────────────┐    │
    │  │ Whisper STT │         │ Text Parser │───▶│ Claude API  │    │
    │  └─────────────┘         └─────────────┘    └──────┬──────┘    │
    └─────────────────────────────────────────────────────┼───────────┘
                                                          │
                                                          ▼
                                              ┌───────────────────┐
                                              │   Unified Task    │
                                              │     Storage       │
                                              └───────────────────┘
```

## Implementation Details

### 1. Telegram Bot Integration

#### Setup
```python
# telegram_bot.py
import os
import json
import redis
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

class TelegramTaskBot:
    def __init__(self):
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.redis_client = redis.from_url(os.getenv('REDIS_URL'))
        self.allowed_users = os.getenv('TELEGRAM_ALLOWED_USERS', '').split(',')
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user_id = str(update.effective_user.id)
        
        if user_id not in self.allowed_users:
            await update.message.reply_text("Sorry, you're not authorized to use this bot.")
            return
            
        await update.message.reply_text(
            "Welcome to Mike Logger! 🎤\n\n"
            "Send me tasks, reminders, or ideas and I'll add them to your system.\n\n"
            "Commands:\n"
            "/task <message> - Add a task\n"
            "/reminder <message> - Add a reminder\n"
            "/idea <message> - Add an idea\n"
            "/status - Check processing status"
        )
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming messages"""
        user_id = str(update.effective_user.id)
        
        if user_id not in self.allowed_users:
            return
            
        message_text = update.message.text
        message_type = self._classify_message(message_text)
        
        # Create task object
        task = {
            'id': f'telegram_{update.message.message_id}',
            'source': 'telegram',
            'user_id': user_id,
            'timestamp': datetime.now().isoformat(),
            'text': message_text,
            'type': message_type,
            'metadata': {
                'chat_id': update.effective_chat.id,
                'message_id': update.message.message_id,
                'user_name': update.effective_user.full_name
            }
        }
        
        # Queue for processing
        self._queue_task(task)
        
        await update.message.reply_text(
            f"✅ {message_type.title()} received!\n"
            f"I'll process this and add it to your task list."
        )
    
    def _classify_message(self, text):
        """Simple classification of message type"""
        text_lower = text.lower()
        
        if any(word in text_lower for word in ['remind', 'reminder', 'tomorrow', 'later']):
            return 'reminder'
        elif any(word in text_lower for word in ['idea', 'what if', 'maybe', 'could']):
            return 'idea'
        elif '?' in text:
            return 'question'
        else:
            return 'task'
    
    def _queue_task(self, task):
        """Queue task for processing"""
        queue_key = f"message_queue:telegram:{task['id']}"
        
        self.redis_client.hset(queue_key, mapping={
            'data': json.dumps(task),
            'status': 'pending',
            'created_at': datetime.now().isoformat()
        })
        
        # Add to processing queue
        self.redis_client.lpush('message_processing_queue', queue_key)
        
        # Set expiry
        self.redis_client.expire(queue_key, 86400)  # 24 hours
    
    def run(self):
        """Start the bot"""
        app = Application.builder().token(self.token).build()
        
        # Command handlers
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("task", self.handle_command))
        app.add_handler(CommandHandler("reminder", self.handle_command))
        app.add_handler(CommandHandler("idea", self.handle_command))
        app.add_handler(CommandHandler("status", self.status))
        
        # Message handler
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        # Start polling
        app.run_polling()
```

#### Docker Service
```yaml
# Add to docker-compose.yml
telegram-bot:
  build:
    context: .
    dockerfile: Dockerfile.telegram
  container_name: mike-logger-telegram
  environment:
    - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
    - TELEGRAM_ALLOWED_USERS=${TELEGRAM_ALLOWED_USERS}
    - REDIS_URL=redis://redis:6379
  depends_on:
    - redis
  restart: unless-stopped
```

### 2. WhatsApp Business API Integration

#### Setup Using Twilio
```python
# whatsapp_webhook.py
from flask import Flask, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse
import redis
import json
from datetime import datetime

app = Flask(__name__)
redis_client = redis.from_url(os.getenv('REDIS_URL'))

@app.route('/whatsapp/webhook', methods=['POST'])
def whatsapp_webhook():
    """Handle incoming WhatsApp messages via Twilio"""
    incoming_msg = request.values.get('Body', '').strip()
    from_number = request.values.get('From', '')
    
    # Verify sender is authorized
    if not is_authorized_number(from_number):
        return '', 200
    
    # Create task from message
    task = {
        'id': f'whatsapp_{request.values.get("MessageSid")}',
        'source': 'whatsapp',
        'sender': from_number,
        'timestamp': datetime.now().isoformat(),
        'text': incoming_msg,
        'type': classify_message(incoming_msg),
        'metadata': {
            'message_sid': request.values.get('MessageSid'),
            'account_sid': request.values.get('AccountSid')
        }
    }
    
    # Queue for processing
    queue_task(task)
    
    # Send response
    resp = MessagingResponse()
    resp.message(f"✅ Got it! I'll add this {task['type']} to your list.")
    
    return str(resp)

def is_authorized_number(number):
    """Check if number is authorized"""
    allowed_numbers = os.getenv('WHATSAPP_ALLOWED_NUMBERS', '').split(',')
    return any(allowed in number for allowed in allowed_numbers)
```

#### Alternative: WhatsApp Business Cloud API
```python
# whatsapp_cloud_api.py
import requests
import os

class WhatsAppCloudAPI:
    def __init__(self):
        self.token = os.getenv('WHATSAPP_ACCESS_TOKEN')
        self.phone_number_id = os.getenv('WHATSAPP_PHONE_NUMBER_ID')
        self.base_url = f"https://graph.facebook.com/v17.0/{self.phone_number_id}"
        
    def setup_webhook(self):
        """Configure webhook for incoming messages"""
        # This would be set up in Meta Business Manager
        pass
        
    def send_message(self, to_number, message):
        """Send WhatsApp message"""
        url = f"{self.base_url}/messages"
        headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }
        
        data = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "text",
            "text": {"body": message}
        }
        
        response = requests.post(url, headers=headers, json=data)
        return response.json()
```

### 3. SMS Integration (Twilio)

```python
# sms_webhook.py
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import redis
import json
from datetime import datetime

app = Flask(__name__)
redis_client = redis.from_url(os.getenv('REDIS_URL'))

@app.route('/sms/webhook', methods=['POST'])
def sms_webhook():
    """Handle incoming SMS messages"""
    body = request.values.get('Body', '').strip()
    from_number = request.values.get('From', '')
    
    # Create task
    task = {
        'id': f'sms_{request.values.get("MessageSid")}',
        'source': 'sms',
        'sender': from_number,
        'timestamp': datetime.now().isoformat(),
        'text': body,
        'type': classify_message(body),
        'metadata': {
            'message_sid': request.values.get('MessageSid'),
            'from_city': request.values.get('FromCity', ''),
            'from_country': request.values.get('FromCountry', '')
        }
    }
    
    # Queue for processing
    queue_task(task)
    
    # Send response
    resp = MessagingResponse()
    resp.message("Task received! I'll process this for you.")
    
    return str(resp)
```

### 4. Unified Message Processor

```python
# message_processor.py
import json
import redis
from datetime import datetime
from anthropic import Anthropic

class MessageProcessor:
    def __init__(self):
        self.redis_client = redis.from_url(os.getenv('REDIS_URL'))
        self.anthropic_client = Anthropic()
        
    def process_message_queue(self):
        """Process messages from all sources"""
        while True:
            # Get next message from queue
            queue_key = self.redis_client.rpop('message_processing_queue')
            
            if not queue_key:
                time.sleep(5)
                continue
                
            # Get message data
            message_data = self.redis_client.hgetall(queue_key)
            task = json.loads(message_data['data'])
            
            # Process based on source
            if task['source'] in ['telegram', 'whatsapp', 'sms']:
                processed_task = self.process_text_message(task)
            
            # Save to unified task storage
            self.save_task(processed_task)
            
            # Update status
            self.redis_client.hset(queue_key, 'status', 'completed')
    
    def process_text_message(self, task):
        """Process text message into structured task"""
        # Use Claude to extract structured information
        prompt = f"""
        Analyze this message and extract task information:
        
        Message: "{task['text']}"
        Source: {task['source']}
        
        Extract:
        1. Task type (task, reminder, idea, question)
        2. Priority (high, medium, low)
        3. Any deadline mentioned
        4. Key entities (people, projects, topics)
        5. Suggested actions
        
        Return as JSON.
        """
        
        response = self.anthropic_client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Parse response and merge with original task
        extracted = json.loads(response.content[0].text)
        
        return {
            **task,
            'processed_at': datetime.now().isoformat(),
            'extracted': extracted,
            'status': 'ready'
        }
    
    def save_task(self, task):
        """Save to unified task storage"""
        task_file = f"data/tasks/message_{task['source']}_{task['id']}.json"
        
        with open(task_file, 'w') as f:
            json.dump(task, f, indent=2)
```

## Configuration

### Environment Variables
```bash
# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_ALLOWED_USERS=123456789,987654321  # Telegram user IDs

# WhatsApp (Twilio)
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_WHATSAPP_NUMBER=+14155238886  # Twilio sandbox or your number
WHATSAPP_ALLOWED_NUMBERS=+1234567890,+0987654321

# WhatsApp (Cloud API)
WHATSAPP_ACCESS_TOKEN=your_access_token
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id
WHATSAPP_WEBHOOK_VERIFY_TOKEN=your_verify_token

# SMS (Twilio)
TWILIO_SMS_NUMBER=+1234567890
SMS_ALLOWED_NUMBERS=+1234567890,+0987654321
```

### Docker Compose Addition
```yaml
# messaging-services.yml
version: '3.8'

services:
  telegram-bot:
    build:
      context: .
      dockerfile: Dockerfile.messaging
    container_name: mike-logger-telegram
    environment:
      - SERVICE_TYPE=telegram
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - TELEGRAM_ALLOWED_USERS=${TELEGRAM_ALLOWED_USERS}
      - REDIS_URL=redis://redis:6379
    depends_on:
      - redis
    restart: unless-stopped

  whatsapp-webhook:
    build:
      context: .
      dockerfile: Dockerfile.messaging
    container_name: mike-logger-whatsapp
    environment:
      - SERVICE_TYPE=whatsapp
      - REDIS_URL=redis://redis:6379
    ports:
      - "5000:5000"  # Webhook endpoint
    depends_on:
      - redis
    restart: unless-stopped

  sms-webhook:
    build:
      context: .
      dockerfile: Dockerfile.messaging
    container_name: mike-logger-sms
    environment:
      - SERVICE_TYPE=sms
      - REDIS_URL=redis://redis:6379
    ports:
      - "5001:5001"  # Webhook endpoint
    depends_on:
      - redis
    restart: unless-stopped

  message-processor:
    build:
      context: .
      dockerfile: Dockerfile.messaging
    container_name: mike-logger-message-processor
    environment:
      - SERVICE_TYPE=processor
      - REDIS_URL=redis://redis:6379
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    volumes:
      - ./data/tasks:/app/data/tasks
    depends_on:
      - redis
    restart: unless-stopped
```

## Security Considerations

### 1. Authentication
- **Telegram**: Whitelist user IDs
- **WhatsApp**: Verify sender phone numbers
- **SMS**: Implement OTP verification for first-time users

### 2. Rate Limiting
```python
def rate_limit_check(user_id, source):
    """Check if user has exceeded rate limit"""
    key = f"rate_limit:{source}:{user_id}"
    count = redis_client.incr(key)
    
    if count == 1:
        redis_client.expire(key, 3600)  # 1 hour window
    
    max_messages = {
        'telegram': 100,
        'whatsapp': 50,
        'sms': 20
    }
    
    return count <= max_messages.get(source, 50)
```

### 3. Data Privacy
- Encrypt message content at rest
- Implement data retention policies
- Allow users to delete their data
- Don't log sensitive information

## Usage Examples

### Telegram
```
User: Remind me to call Sarah about the project tomorrow at 3pm
Bot: ✅ Reminder received! I'll process this and add it to your task list.

User: /task Review Q4 budget proposals by Friday
Bot: ✅ Task received! I'll process this and add it to your task list.

User: /idea What if we implemented voice commands for the smart home system?
Bot: ✅ Idea received! I'll process this and add it to your task list.
```

### WhatsApp
```
User: Pick up groceries: milk, bread, eggs
Bot: ✅ Got it! I'll add this task to your list.

User: Meeting with John next Tuesday 2pm
Bot: ✅ Got it! I'll add this reminder to your list.
```

### SMS
```
User: Call dentist tomorrow
Bot: Task received! I'll process this for you.
```

## Advanced Features

### 1. Natural Language Processing
```python
def enhanced_message_processing(text):
    """Enhanced NLP for better task extraction"""
    # Detect urgency
    urgent_keywords = ['urgent', 'asap', 'emergency', 'critical']
    is_urgent = any(keyword in text.lower() for keyword in urgent_keywords)
    
    # Extract dates/times
    # Use dateutil or similar for parsing
    
    # Extract people mentions
    # Use regex or NER for name extraction
    
    # Categorize by project/context
    # Use keyword matching or classification
```

### 2. Conversation Context
```python
class ConversationManager:
    def __init__(self):
        self.contexts = {}  # user_id -> conversation history
        
    def add_message(self, user_id, message):
        if user_id not in self.contexts:
            self.contexts[user_id] = []
        
        self.contexts[user_id].append({
            'timestamp': datetime.now(),
            'message': message
        })
        
        # Keep only last 10 messages
        self.contexts[user_id] = self.contexts[user_id][-10:]
    
    def get_context(self, user_id):
        return self.contexts.get(user_id, [])
```

### 3. Multi-Modal Responses
```python
def send_task_summary(user_id, source):
    """Send daily task summary to user"""
    tasks = get_user_tasks(user_id)
    
    if source == 'telegram':
        # Send formatted message with inline keyboard
        send_telegram_summary(user_id, tasks)
    elif source == 'whatsapp':
        # Send text summary with emojis
        send_whatsapp_summary(user_id, tasks)
    elif source == 'sms':
        # Send concise text summary
        send_sms_summary(user_id, tasks)
```

## Integration with Mike Logger

### Unified Task Format
```json
{
  "id": "unique_id",
  "source": "voice|telegram|whatsapp|sms",
  "source_metadata": {
    "audio_file": "path/to/file.wav",  // for voice
    "message_id": "telegram_123",       // for messages
    "sender": "user_identifier"
  },
  "timestamp": "2024-01-07T10:30:00Z",
  "raw_input": "original text or transcript",
  "processed": {
    "type": "task|reminder|idea|question",
    "content": "cleaned task description",
    "priority": "high|medium|low",
    "deadline": "2024-01-08T15:00:00Z",
    "entities": {
      "people": ["Sarah"],
      "projects": ["Q4 Budget"],
      "locations": ["office"]
    },
    "confidence": 0.95
  },
  "status": "pending|completed|cancelled",
  "created_at": "2024-01-07T10:30:00Z",
  "updated_at": "2024-01-07T10:30:00Z"
}
```

This integration creates a powerful multi-modal task capture system where users can seamlessly switch between voice and text input based on their current context and preferences.