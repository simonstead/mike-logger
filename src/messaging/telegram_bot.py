#!/usr/bin/env python3
"""
Telegram Bot for Mike Logger
Allows users to submit tasks via Telegram messages
"""
import os
import json
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any

import redis
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logger = logging.getLogger(__name__)

class MikeLoggerTelegramBot:
    def __init__(self):
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
            
        self.redis_client = redis.from_url(os.getenv('REDIS_URL', 'redis://localhost:6379'), decode_responses=True)
        
        # Parse allowed users
        allowed_users_str = os.getenv('TELEGRAM_ALLOWED_USERS', '')
        self.allowed_users = [user.strip() for user in allowed_users_str.split(',') if user.strip()]
        
        if not self.allowed_users:
            logger.warning("No TELEGRAM_ALLOWED_USERS configured - bot will reject all users")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user_id = str(update.effective_user.id)
        
        if not self._is_authorized_user(user_id):
            await update.message.reply_text(
                "🚫 Sorry, you're not authorized to use this bot.\n"
                "Contact the administrator to get access."
            )
            return
        
        welcome_message = (
            "🎤 **Welcome to Mike Logger!**\n\n"
            "I can help you capture tasks, reminders, and ideas on the go.\n\n"
            "**How to use:**\n"
            "• Just send me any message and I'll process it\n"
            "• I'll automatically classify it as a task, reminder, or idea\n"
            "• Everything gets added to your unified task system\n\n"
            "**Commands:**\n"
            "/task <message> - Explicitly mark as task\n"
            "/reminder <message> - Explicitly mark as reminder\n"
            "/idea <message> - Explicitly mark as idea\n"
            "/status - Check recent activity\n"
            "/help - Show this message\n\n"
            "Try sending: *Remind me to call Sarah tomorrow*"
        )
        
        await update.message.reply_text(welcome_message, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        await self.start_command(update, context)
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        user_id = str(update.effective_user.id)
        
        if not self._is_authorized_user(user_id):
            return
        
        # Get recent tasks from Redis
        try:
            recent_keys = self.redis_client.keys(f"message_queue:telegram:*")
            recent_count = len(recent_keys)
            
            # Get processing queue size
            queue_size = self.redis_client.llen('message_processing_queue')
            
            status_message = (
                f"📊 **Mike Logger Status**\n\n"
                f"• Recent Telegram messages: {recent_count}\n"
                f"• Messages in processing queue: {queue_size}\n"
                f"• Your User ID: `{user_id}`\n\n"
                f"System is {'🟢 running normally' if queue_size < 10 else '🟡 processing backlog'}"
            )
            
            await update.message.reply_text(status_message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            await update.message.reply_text("❌ Error getting status. Please try again later.")
    
    async def explicit_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle explicit type commands (/task, /reminder, /idea)"""
        user_id = str(update.effective_user.id)
        
        if not self._is_authorized_user(user_id):
            return
        
        command = update.message.text.split()[0].lower()
        message_text = ' '.join(update.message.text.split()[1:])
        
        if not message_text:
            await update.message.reply_text(
                f"Please provide a message after the {command} command.\n"
                f"Example: `{command} Review quarterly reports`",
                parse_mode='Markdown'
            )
            return
        
        # Determine type from command
        task_type = {
            '/task': 'task',
            '/reminder': 'reminder', 
            '/idea': 'idea'
        }.get(command, 'task')
        
        await self._process_message(update, message_text, task_type)
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle regular text messages"""
        user_id = str(update.effective_user.id)
        
        if not self._is_authorized_user(user_id):
            await update.message.reply_text("🚫 Unauthorized access.")
            return
        
        message_text = update.message.text.strip()
        
        # Auto-classify message type
        task_type = self._classify_message(message_text)
        
        await self._process_message(update, message_text, task_type)
    
    async def _process_message(self, update: Update, message_text: str, task_type: str):
        """Process and queue a message"""
        try:
            # Create task object
            task = {
                'id': f'telegram_{update.message.message_id}_{int(datetime.now().timestamp())}',
                'source': 'telegram',
                'user_id': str(update.effective_user.id),
                'timestamp': datetime.now().isoformat(),
                'text': message_text,
                'type': task_type,
                'metadata': {
                    'chat_id': update.effective_chat.id,
                    'message_id': update.message.message_id,
                    'user_name': update.effective_user.full_name or 'Unknown',
                    'username': update.effective_user.username
                }
            }
            
            # Queue for processing
            success = self._queue_task(task)
            
            if success:
                # Send confirmation with appropriate emoji
                emoji_map = {
                    'task': '✅',
                    'reminder': '⏰', 
                    'idea': '💡',
                    'question': '❓'
                }
                
                emoji = emoji_map.get(task_type, '✅')
                
                await update.message.reply_text(
                    f"{emoji} **{task_type.title()} received!**\n"
                    f"I'll process this and add it to your system.\n\n"
                    f"Message: _{message_text}_",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    "❌ Sorry, there was an error processing your message. "
                    "Please try again in a moment."
                )
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            await update.message.reply_text(
                "❌ An error occurred while processing your message. "
                "The administrators have been notified."
            )
    
    def _is_authorized_user(self, user_id: str) -> bool:
        """Check if user is authorized"""
        return user_id in self.allowed_users
    
    def _classify_message(self, text: str) -> str:
        """Automatically classify message type based on content"""
        text_lower = text.lower()
        
        # Check for reminder keywords
        reminder_keywords = ['remind', 'reminder', 'remember', 'tomorrow', 'later', 'next week', 'schedule']
        if any(word in text_lower for word in reminder_keywords):
            return 'reminder'
        
        # Check for idea keywords
        idea_keywords = ['idea', 'what if', 'maybe', 'could we', 'suggestion', 'thought', 'concept']
        if any(word in text_lower for word in idea_keywords):
            return 'idea'
        
        # Check for questions
        if '?' in text or text_lower.startswith(('how', 'what', 'when', 'where', 'why', 'who')):
            return 'question'
        
        # Default to task
        return 'task'
    
    def _queue_task(self, task: Dict[str, Any]) -> bool:
        """Queue task for processing"""
        try:
            queue_key = f"message_queue:telegram:{task['id']}"
            
            # Store task data in Redis hash
            self.redis_client.hset(queue_key, mapping={
                'data': json.dumps(task),
                'status': 'pending',
                'created_at': datetime.now().isoformat(),
                'source': 'telegram'
            })
            
            # Add to processing queue
            self.redis_client.lpush('message_processing_queue', queue_key)
            
            # Set expiry (24 hours)
            self.redis_client.expire(queue_key, 86400)
            
            logger.info(f"Queued Telegram task: {task['id']}")
            return True
            
        except Exception as e:
            logger.error(f"Error queuing task: {e}")
            return False
    
    def run(self):
        """Start the bot"""
        logger.info("Starting Telegram bot...")
        
        try:
            # Create application
            app = Application.builder().token(self.token).build()
            
            # Add command handlers
            app.add_handler(CommandHandler("start", self.start_command))
            app.add_handler(CommandHandler("help", self.help_command))
            app.add_handler(CommandHandler("status", self.status_command))
            app.add_handler(CommandHandler("task", self.explicit_command))
            app.add_handler(CommandHandler("reminder", self.explicit_command))
            app.add_handler(CommandHandler("idea", self.explicit_command))
            
            # Add message handler for regular text
            app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
            
            logger.info(f"Bot configured for {len(self.allowed_users)} authorized users")
            logger.info("Starting polling...")
            
            # Start polling
            app.run_polling(allowed_updates=Update.ALL_TYPES)
            
        except Exception as e:
            logger.error(f"Error starting bot: {e}")
            raise

def main():
    """Main entry point"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    bot = MikeLoggerTelegramBot()
    bot.run()

if __name__ == '__main__':
    main()