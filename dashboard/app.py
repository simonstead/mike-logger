#!/usr/bin/env python3
"""
Mike Logger Dashboard - Web interface for monitoring
"""
import os
import json
import redis
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_socketio import SocketIO, emit
import logging
import tempfile
import shutil
from collections import defaultdict
import threading
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder='/app/templates')
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'dev-key-change-in-production')

# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Initialize Redis connection
try:
    redis_url = os.getenv('REDIS_URL', 'redis://redis:6379')
    redis_client = redis.from_url(redis_url, decode_responses=True)
    redis_client.ping()
    logger.info("Redis connection established")
except Exception as e:
    logger.warning(f"Redis not available: {e}")
    redis_client = None

# Data directories
DATA_DIR = Path('/app/data')
AUDIO_DIR = DATA_DIR / 'audio'
TRANSCRIPTS_DIR = DATA_DIR / 'transcripts'
TASKS_DIR = DATA_DIR / 'tasks'
DOCS_DIR = Path('/app/docs')

@app.route('/')
def index():
    """Dashboard home page"""
    stats = get_system_stats()
    return render_template('dashboard.html', stats=stats)

@app.route('/v2')
def index_v2():
    """Enhanced dashboard with live updates"""
    return render_template('dashboard_v2.html')

@app.route('/api/stats')
def api_stats():
    """Get system statistics"""
    return jsonify(get_system_stats())

@app.route('/api/files')
def api_files():
    """Get file listings"""
    file_type = request.args.get('type', 'audio')
    
    if file_type == 'audio':
        files = list_files(AUDIO_DIR, '*.wav')
    elif file_type == 'transcripts':
        files = list_files(TRANSCRIPTS_DIR, '*.json')
    elif file_type == 'tasks':
        files = list_files(TASKS_DIR, '*.json')
    else:
        files = []
    
    return jsonify(files)

@app.route('/api/file/<path:filename>')
def api_file_content(filename):
    """Get file content"""
    try:
        # Security check - only allow files in data directory
        file_path = Path(f'/app/data/{filename}')
        if not str(file_path.resolve()).startswith('/app/data/'):
            return jsonify({'error': 'Access denied'}), 403
        
        if not file_path.exists():
            return jsonify({'error': 'File not found'}), 404
        
        if file_path.suffix == '.json':
            with open(file_path, 'r') as f:
                content = json.load(f)
        else:
            with open(file_path, 'r') as f:
                content = f.read()
        
        return jsonify({
            'filename': filename,
            'content': content,
            'size': file_path.stat().st_size,
            'modified': file_path.stat().st_mtime
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/processing-status')
def api_processing_status():
    """Get processing status from Redis"""
    if not redis_client:
        return jsonify({'error': 'Redis not available'}), 503
    
    try:
        # Get all processing keys
        keys = redis_client.keys('processing:*')
        status_data = []
        
        for key in keys:
            data = redis_client.hgetall(key)
            filename = key.replace('processing:', '')
            
            status_data.append({
                'filename': filename,
                'status': data.get('status', 'unknown'),
                'updated_at': data.get('updated_at'),
                'data': json.loads(data.get('data', '{}'))
            })
        
        return jsonify(status_data)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload-audio', methods=['POST'])
def upload_audio():
    """Upload audio file from web interface"""
    try:
        logger.info("=== Audio upload request received ===")
        logger.info(f"Request files: {request.files}")
        logger.info(f"Request form: {request.form}")
        logger.info(f"Request content-type: {request.content_type}")
        
        if 'audio' not in request.files:
            logger.error("No 'audio' field in request.files")
            return jsonify({'error': 'No audio file provided'}), 400
        
        audio_file = request.files['audio']
        logger.info(f"Audio file: {audio_file}")
        logger.info(f"Audio filename: {audio_file.filename}")
        logger.info(f"Audio content-type: {audio_file.content_type}")
        
        if audio_file.filename == '':
            logger.error("Empty filename")
            return jsonify({'error': 'No file selected'}), 400
        
        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"web-capture-{timestamp}.wav"
        logger.info(f"Generated filename: {filename}")
        
        # Check audio directory
        logger.info(f"Audio directory: {AUDIO_DIR}")
        logger.info(f"Audio directory exists: {AUDIO_DIR.exists()}")
        logger.info(f"Audio directory is writable: {os.access(AUDIO_DIR, os.W_OK)}")
        
        # Ensure audio directory exists
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        
        # Save to audio directory
        audio_path = AUDIO_DIR / filename
        logger.info(f"Target path: {audio_path}")
        
        # Save the uploaded file
        try:
            # Save directly without temp file
            audio_file.save(str(audio_path))
            logger.info(f"File saved successfully to {audio_path}")
        except Exception as save_error:
            logger.error(f"Error saving file: {save_error}")
            logger.error(f"Current working directory: {os.getcwd()}")
            logger.error(f"Directory permissions: {oct(os.stat(AUDIO_DIR).st_mode)}")
            raise save_error
        
        # Verify file was saved
        if not audio_path.exists():
            logger.error(f"File not found after save: {audio_path}")
            raise Exception("File save verification failed")
        
        file_size = audio_path.stat().st_size
        logger.info(f"Audio file uploaded successfully: {filename} ({file_size} bytes)")
        
        # Update Redis if available
        if redis_client:
            try:
                redis_client.hset(f"processing:{filename}", mapping={
                    'status': 'pending',
                    'uploaded_at': datetime.now().isoformat(),
                    'source': 'web-upload',
                    'data': json.dumps({'filename': filename})
                })
                redis_client.expire(f"processing:{filename}", 86400)  # 24 hours
                logger.info("Redis updated successfully")
            except Exception as e:
                logger.warning(f"Failed to update Redis: {e}")
        
        return jsonify({
            'success': True,
            'filename': filename,
            'size': file_size,
            'message': 'Audio file uploaded successfully'
        })
        
    except Exception as e:
        logger.error(f"=== Error uploading audio ===")
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error message: {str(e)}")
        logger.error(f"Error details:", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/executions')
def get_executions():
    """Get task execution history"""
    try:
        if not redis_client:
            return jsonify({'error': 'Redis not available'}), 503
        
        # Get recent execution keys
        execution_keys = redis_client.lrange('execution_history', 0, 49)  # Last 50
        executions = []
        
        for key in execution_keys:
            data = redis_client.hgetall(key)
            if data:
                executions.append({
                    'id': key.replace('execution:', ''),
                    'status': data.get('status'),
                    'updated_at': data.get('updated_at'),
                    'task': json.loads(data.get('task', '{}')),
                    'data': json.loads(data.get('data', '{}'))
                })
        
        return jsonify(executions)
    
    except Exception as e:
        logger.error(f"Error getting executions: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/approvals')
def get_pending_approvals():
    """Get tasks pending approval"""
    try:
        if not redis_client:
            return jsonify([])
        
        approval_keys = redis_client.keys('approval_queue:*')
        approvals = []
        
        for key in approval_keys:
            data = redis_client.hgetall(key)
            if data:
                approvals.append({
                    'id': key.replace('approval_queue:', ''),
                    'task': json.loads(data.get('task', '{}')),
                    'context': json.loads(data.get('context', '{}')),
                    'queued_at': data.get('queued_at')
                })
        
        return jsonify(approvals)
    
    except Exception as e:
        logger.error(f"Error getting approvals: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/approvals/<approval_id>', methods=['POST'])
def handle_approval(approval_id):
    """Approve or reject a task"""
    try:
        if not redis_client:
            return jsonify({'error': 'Redis not available'}), 503
        
        action = request.json.get('action')  # 'approve' or 'reject'
        
        if action not in ['approve', 'reject']:
            return jsonify({'error': 'Invalid action'}), 400
        
        approval_key = f"approval_queue:{approval_id}"
        
        if action == 'approve':
            # Move to approved queue for executor to pick up
            data = redis_client.hgetall(approval_key)
            if data:
                approved_key = f"approved_tasks:{approval_id}"
                redis_client.hset(approved_key, mapping=data)
                redis_client.expire(approved_key, 3600)  # 1 hour to execute
        
        # Remove from approval queue
        redis_client.delete(approval_key)
        
        return jsonify({'success': True, 'action': action})
    
    except Exception as e:
        logger.error(f"Error handling approval: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/submit-text-task', methods=['POST'])
def submit_text_task():
    """Submit a text task directly from the web interface"""
    try:
        data = request.json
        content = data.get('content', '').strip()
        priority = data.get('priority', 'medium')
        source = data.get('source', 'web-text-input')
        
        if not content:
            return jsonify({'error': 'Task content is required'}), 400
        
        # Create task structure
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"text_task_{timestamp}.json"
        
        task_data = {
            'source_transcript': f'/app/data/transcripts/{source}_{timestamp}.json',
            'extracted_at': datetime.now().isoformat(),
            'task_count': 1,
            'tasks': [{
                'type': 'task',
                'content': content,
                'priority': priority,
                'deadline': None,
                'confidence': 1.0,  # High confidence for manual input
                'entities': {
                    'action': 'process',
                    'topic': 'manual task',
                    'source': source
                }
            }]
        }
        
        # Save task file
        task_path = TASKS_DIR / filename
        with open(task_path, 'w') as f:
            json.dump(task_data, f, indent=2)
        
        logger.info(f"Text task submitted: {filename}")
        
        # Update Redis if available
        if redis_client:
            try:
                redis_client.hset(f"processing:{filename}", mapping={
                    'status': 'pending',
                    'submitted_at': datetime.now().isoformat(),
                    'source': source,
                    'priority': priority,
                    'data': json.dumps({'content': content})
                })
                redis_client.expire(f"processing:{filename}", 86400)
            except Exception as e:
                logger.warning(f"Failed to update Redis: {e}")
        
        return jsonify({
            'success': True,
            'filename': filename,
            'message': 'Task submitted successfully'
        })
        
    except Exception as e:
        logger.error(f"Error submitting text task: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/projects')
def list_projects():
    """List all projects and their files"""
    try:
        projects_dir = Path('/app/projects')
        projects = []
        
        if projects_dir.exists():
            for project_path in projects_dir.iterdir():
                if project_path.is_dir() and not project_path.name.startswith('.'):
                    file_count = sum(1 for _ in project_path.rglob('*') if _.is_file())
                    projects.append({
                        'name': project_path.name,
                        'path': str(project_path),
                        'file_count': file_count,
                        'modified': project_path.stat().st_mtime
                    })
        
        return jsonify(sorted(projects, key=lambda p: p['name']))
    
    except Exception as e:
        logger.error(f"Error listing projects: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})

@app.route('/api/activity')
def get_activity():
    """Get recent activity timeline"""
    try:
        activities = []
        
        # Get recent files from each directory
        now = datetime.now()
        cutoff_time = now - timedelta(hours=24)
        
        # Check audio files
        for audio_file in sorted(AUDIO_DIR.glob('*.wav'), key=lambda f: f.stat().st_mtime, reverse=True)[:5]:
            if datetime.fromtimestamp(audio_file.stat().st_mtime) > cutoff_time:
                activities.append({
                    'type': 'audio',
                    'title': 'Audio Captured',
                    'description': f'Recorded {audio_file.name}',
                    'timestamp': datetime.fromtimestamp(audio_file.stat().st_mtime).isoformat()
                })
        
        # Check transcripts
        for transcript_file in sorted(TRANSCRIPTS_DIR.glob('*.json'), key=lambda f: f.stat().st_mtime, reverse=True)[:5]:
            if datetime.fromtimestamp(transcript_file.stat().st_mtime) > cutoff_time:
                activities.append({
                    'type': 'transcript',
                    'title': 'Audio Transcribed',
                    'description': f'Transcribed to {transcript_file.name}',
                    'timestamp': datetime.fromtimestamp(transcript_file.stat().st_mtime).isoformat()
                })
        
        # Check tasks
        for task_file in sorted(TASKS_DIR.glob('*.json'), key=lambda f: f.stat().st_mtime, reverse=True)[:5]:
            if datetime.fromtimestamp(task_file.stat().st_mtime) > cutoff_time:
                try:
                    with open(task_file, 'r') as f:
                        task_data = json.load(f)
                        task_count = task_data.get('task_count', 0)
                        activities.append({
                            'type': 'task',
                            'title': 'Tasks Extracted',
                            'description': f'{task_count} task(s) extracted from {task_file.name}',
                            'timestamp': datetime.fromtimestamp(task_file.stat().st_mtime).isoformat()
                        })
                except:
                    pass
        
        # Sort by timestamp
        activities.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return jsonify(activities[:20])  # Return last 20 activities
        
    except Exception as e:
        logger.error(f"Error getting activity: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/projects/<project_name>')
def get_project_details(project_name):
    """Get details about a specific project"""
    try:
        project_path = Path(f'/app/projects/{project_name}')
        if not project_path.exists():
            return jsonify({'error': 'Project not found'}), 404
        
        files = []
        for file_path in project_path.rglob('*'):
            if file_path.is_file() and not file_path.name.startswith('.'):
                files.append({
                    'name': file_path.name,
                    'path': str(file_path.relative_to(Path('/app'))),
                    'size': file_path.stat().st_size,
                    'modified': datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                })
        
        return jsonify({
            'name': project_name,
            'path': str(project_path),
            'files': sorted(files, key=lambda f: f['modified'], reverse=True)
        })
        
    except Exception as e:
        logger.error(f"Error getting project details: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/messaging')
def messaging_status():
    """Messaging configuration and status page"""
    try:
        # Get messaging configuration (without secrets)
        messaging_config = {
            'telegram': {
                'enabled': bool(os.getenv('TELEGRAM_BOT_TOKEN')),
                'bot_token_set': bool(os.getenv('TELEGRAM_BOT_TOKEN')),
                'allowed_users': os.getenv('TELEGRAM_ALLOWED_USERS', 'Not configured').split(',') if os.getenv('TELEGRAM_ALLOWED_USERS') else [],
                'webhook_configured': False  # Could check Redis for webhook status
            },
            'whatsapp': {
                'enabled': bool(os.getenv('TWILIO_ACCOUNT_SID')),
                'twilio_configured': bool(os.getenv('TWILIO_ACCOUNT_SID') and os.getenv('TWILIO_AUTH_TOKEN')),
                'phone_number': os.getenv('TWILIO_PHONE_NUMBER', 'Not configured'),
                'allowed_numbers': os.getenv('WHATSAPP_ALLOWED_NUMBERS', 'Not configured').split(',') if os.getenv('WHATSAPP_ALLOWED_NUMBERS') else []
            },
            'sms': {
                'enabled': bool(os.getenv('TWILIO_ACCOUNT_SID')),
                'uses_same_config': True  # Uses same Twilio config as WhatsApp
            }
        }
        
        # Get messaging statistics from Redis if available
        messaging_stats = {
            'telegram_messages': 0,
            'whatsapp_messages': 0,
            'sms_messages': 0,
            'last_message': None
        }
        
        if redis_client:
            try:
                # Get message counts
                telegram_count = redis_client.get('stats:telegram:messages') or 0
                whatsapp_count = redis_client.get('stats:whatsapp:messages') or 0
                sms_count = redis_client.get('stats:sms:messages') or 0
                
                messaging_stats.update({
                    'telegram_messages': int(telegram_count) if telegram_count else 0,
                    'whatsapp_messages': int(whatsapp_count) if whatsapp_count else 0,
                    'sms_messages': int(sms_count) if sms_count else 0
                })
                
                # Get recent message activity
                recent_messages = []
                message_keys = redis_client.keys('message:*')[:10]  # Last 10 messages
                for key in message_keys:
                    msg_data = redis_client.hgetall(key)
                    if msg_data:
                        recent_messages.append({
                            'platform': msg_data.get('platform', 'unknown'),
                            'timestamp': msg_data.get('timestamp', ''),
                            'user_id': msg_data.get('user_id', 'anonymous')[:8] + '...',  # Truncate for privacy
                            'type': msg_data.get('type', 'message')
                        })
                
                messaging_stats['recent_messages'] = recent_messages
                
            except Exception as e:
                logger.warning(f"Failed to get messaging stats from Redis: {e}")
        
        # Create HTML page
        html = '''
<!DOCTYPE html>
<html>
<head>
    <title>Messaging Status - Mike Logger</title>
    <style>
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
            max-width: 1200px; 
            margin: 0 auto; 
            padding: 2rem; 
            background: #f5f5f5; 
        }
        .header {
            background: #2563eb;
            color: white;
            padding: 1rem 2rem;
            margin: -2rem -2rem 2rem -2rem;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .header h1 { margin: 0; font-size: 1.8rem; }
        .nav { display: flex; gap: 0.5rem; }
        .nav a {
            color: white;
            text-decoration: none;
            padding: 0.5rem 1rem;
            background: rgba(255,255,255,0.2);
            border-radius: 4px;
        }
        .nav a:hover { background: rgba(255,255,255,0.3); }
        
        .platform-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }
        
        .platform-card {
            background: white;
            padding: 1.5rem;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        
        .platform-card h2 {
            margin-top: 0;
            color: #2563eb;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        .status-badge {
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 999px;
            font-size: 0.875rem;
            font-weight: bold;
        }
        
        .status-enabled {
            background: #10b981;
            color: white;
        }
        
        .status-disabled {
            background: #ef4444;
            color: white;
        }
        
        .status-partial {
            background: #f59e0b;
            color: white;
        }
        
        .config-item {
            margin: 1rem 0;
            padding: 0.75rem;
            background: #f9fafb;
            border-radius: 4px;
        }
        
        .config-label {
            font-weight: bold;
            color: #666;
            font-size: 0.875rem;
        }
        
        .config-value {
            margin-top: 0.25rem;
        }
        
        .stats-section {
            background: white;
            padding: 1.5rem;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 2rem;
        }
        
        .stat-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-top: 1rem;
        }
        
        .stat-item {
            text-align: center;
            padding: 1rem;
            background: #f3f4f6;
            border-radius: 4px;
        }
        
        .stat-value {
            font-size: 2rem;
            font-weight: bold;
            color: #2563eb;
        }
        
        .stat-label {
            color: #666;
            font-size: 0.875rem;
        }
        
        .user-list {
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            margin-top: 0.5rem;
        }
        
        .user-badge {
            background: #e5e7eb;
            padding: 0.25rem 0.75rem;
            border-radius: 4px;
            font-size: 0.875rem;
        }
        
        .warning {
            background: #fef3c7;
            border: 1px solid #fcd34d;
            color: #92400e;
            padding: 1rem;
            border-radius: 4px;
            margin: 1rem 0;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>💬 Messaging Configuration</h1>
        <div class="nav">
            <a href="/">← Dashboard</a>
            <a href="/docs">📚 Documentation</a>
        </div>
    </div>
    '''
        
        # Add statistics
        html += f'''
    <div class="stats-section">
        <h2>📊 Messaging Statistics</h2>
        <div class="stat-grid">
            <div class="stat-item">
                <div class="stat-value">{messaging_stats['telegram_messages']}</div>
                <div class="stat-label">Telegram Messages</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">{messaging_stats['whatsapp_messages']}</div>
                <div class="stat-label">WhatsApp Messages</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">{messaging_stats['sms_messages']}</div>
                <div class="stat-label">SMS Messages</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">{messaging_stats['telegram_messages'] + messaging_stats['whatsapp_messages'] + messaging_stats['sms_messages']}</div>
                <div class="stat-label">Total Messages</div>
            </div>
        </div>
    </div>
    '''
        
        # Add platform cards
        html += '<div class="platform-grid">'
        
        # Telegram card
        telegram_status = 'enabled' if messaging_config['telegram']['enabled'] else 'disabled'
        html += f'''
        <div class="platform-card">
            <h2>
                <span>🤖 Telegram Bot</span>
                <span class="status-badge status-{telegram_status}">{'Enabled' if messaging_config['telegram']['enabled'] else 'Disabled'}</span>
            </h2>
            
            <div class="config-item">
                <div class="config-label">Bot Token</div>
                <div class="config-value">{'✅ Configured' if messaging_config['telegram']['bot_token_set'] else '❌ Not set'}</div>
            </div>
            
            <div class="config-item">
                <div class="config-label">Allowed Users</div>
                <div class="config-value">
        '''
        
        if messaging_config['telegram']['allowed_users']:
            html += '<div class="user-list">'
            for user in messaging_config['telegram']['allowed_users']:
                if user:
                    html += f'<span class="user-badge">{user}</span>'
            html += '</div>'
        else:
            html += '<div class="warning">⚠️ No users configured - bot will reject all messages</div>'
        
        html += '''
            </div>
        </div>
        </div>
        '''
        
        # WhatsApp card
        whatsapp_status = 'enabled' if messaging_config['whatsapp']['enabled'] else 'disabled'
        html += f'''
        <div class="platform-card">
            <h2>
                <span>📱 WhatsApp</span>
                <span class="status-badge status-{whatsapp_status}">{'Enabled' if messaging_config['whatsapp']['enabled'] else 'Disabled'}</span>
            </h2>
            
            <div class="config-item">
                <div class="config-label">Twilio Configuration</div>
                <div class="config-value">{'✅ Configured' if messaging_config['whatsapp']['twilio_configured'] else '❌ Not configured'}</div>
            </div>
            
            <div class="config-item">
                <div class="config-label">Phone Number</div>
                <div class="config-value">{messaging_config['whatsapp']['phone_number']}</div>
            </div>
            
            <div class="config-item">
                <div class="config-label">Allowed Numbers</div>
                <div class="config-value">
        '''
        
        if messaging_config['whatsapp']['allowed_numbers'] and messaging_config['whatsapp']['allowed_numbers'][0]:
            html += '<div class="user-list">'
            for number in messaging_config['whatsapp']['allowed_numbers']:
                if number:
                    html += f'<span class="user-badge">{number}</span>'
            html += '</div>'
        else:
            html += '<div class="warning">⚠️ No numbers configured - all messages will be rejected</div>'
        
        html += '''
            </div>
        </div>
        </div>
        '''
        
        # SMS card
        sms_status = 'enabled' if messaging_config['sms']['enabled'] else 'disabled'
        html += f'''
        <div class="platform-card">
            <h2>
                <span>📨 SMS</span>
                <span class="status-badge status-{sms_status}">{'Enabled' if messaging_config['sms']['enabled'] else 'Disabled'}</span>
            </h2>
            
            <div class="config-item">
                <div class="config-label">Configuration</div>
                <div class="config-value">Uses same Twilio configuration as WhatsApp</div>
            </div>
        </div>
        '''
        
        html += '</div>'  # Close platform-grid
        
        # Add configuration instructions
        html += '''
    <div class="platform-card">
        <h2>⚙️ Configuration Instructions</h2>
        <p>To enable messaging platforms, set the following environment variables in your <code>.env</code> file:</p>
        
        <h3>Telegram Bot</h3>
        <pre>
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
TELEGRAM_ALLOWED_USERS=telegram_user_id_1,telegram_user_id_2
        </pre>
        
        <h3>WhatsApp & SMS (via Twilio)</h3>
        <pre>
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_PHONE_NUMBER=+1234567890
WHATSAPP_ALLOWED_NUMBERS=+1234567890,+0987654321
        </pre>
        
        <p><strong>Security Note:</strong> Always use environment variables for sensitive credentials. Never commit them to version control.</p>
    </div>
</body>
</html>
'''
        
        return html
        
    except Exception as e:
        logger.error(f"Error generating messaging status: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/docs')
def docs_index():
    """Documentation index page"""
    try:
        doc_files = []
        if DOCS_DIR.exists():
            for doc_path in sorted(DOCS_DIR.glob('*.md')):
                doc_files.append({
                    'name': doc_path.stem.replace('-', ' ').title(),
                    'filename': doc_path.name,
                    'size': doc_path.stat().st_size,
                    'modified': datetime.fromtimestamp(doc_path.stat().st_mtime).isoformat()
                })
        
        # Create a simple HTML page for docs
        html = '''
<!DOCTYPE html>
<html>
<head>
    <title>Mike Logger Documentation</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
               max-width: 1200px; margin: 0 auto; padding: 2rem; background: #f5f5f5; }
        h1 { color: #2563eb; }
        .doc-list { background: white; border-radius: 8px; padding: 1.5rem; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .doc-item { display: block; padding: 1rem; margin: 0.5rem 0; background: #f9fafb; 
                    border-radius: 4px; text-decoration: none; color: #333; transition: all 0.2s; }
        .doc-item:hover { background: #e5e7eb; transform: translateX(4px); }
        .back-link { display: inline-block; margin-bottom: 1rem; color: #2563eb; text-decoration: none; }
        .back-link:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <a href="/" class="back-link">← Back to Dashboard</a>
    <h1>📚 Mike Logger Documentation</h1>
    <div class="doc-list">
        <h2>Available Documents</h2>
        '''
        
        for doc in doc_files:
            html += f'<a href="/docs/{doc["filename"]}" class="doc-item">📄 {doc["name"]}</a>\n'
        
        html += '''
    </div>
</body>
</html>
'''
        return html
    except Exception as e:
        logger.error(f"Error listing docs: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/docs/<filename>')
def serve_doc(filename):
    """Serve a documentation file"""
    try:
        # Security check - only allow .md files
        if not filename.endswith('.md'):
            return jsonify({'error': 'Only markdown files allowed'}), 403
        
        # Read and convert markdown to HTML
        doc_path = DOCS_DIR / filename
        if not doc_path.exists():
            return jsonify({'error': 'Document not found'}), 404
        
        content = doc_path.read_text()
        
        # Simple markdown to HTML conversion (basic)
        import re
        html_content = content
        
        # Convert headers
        html_content = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html_content, flags=re.MULTILINE)
        html_content = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html_content, flags=re.MULTILINE)
        html_content = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html_content, flags=re.MULTILINE)
        
        # Convert code blocks
        html_content = re.sub(r'```(\w+)?\n(.*?)```', r'<pre><code class="\1">\2</code></pre>', html_content, flags=re.DOTALL)
        
        # Convert inline code
        html_content = re.sub(r'`([^`]+)`', r'<code>\1</code>', html_content)
        
        # Convert bold
        html_content = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', html_content)
        
        # Convert lists
        html_content = re.sub(r'^- (.+)$', r'<li>\1</li>', html_content, flags=re.MULTILINE)
        html_content = re.sub(r'(<li>.*</li>\n)+', r'<ul>\g<0></ul>', html_content, flags=re.DOTALL)
        
        # Convert paragraphs
        html_content = re.sub(r'\n\n', '</p><p>', html_content)
        html_content = f'<p>{html_content}</p>'
        
        # Create full HTML page
        html = f'''
<!DOCTYPE html>
<html>
<head>
    <title>{filename} - Mike Logger Documentation</title>
    <style>
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
            max-width: 900px; 
            margin: 0 auto; 
            padding: 2rem; 
            line-height: 1.6;
            background: #f5f5f5;
        }}
        .doc-content {{
            background: white;
            padding: 2rem;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1, h2, h3 {{ color: #2563eb; }}
        code {{ 
            background: #f3f4f6; 
            padding: 0.2rem 0.4rem; 
            border-radius: 3px; 
            font-family: monospace;
        }}
        pre {{ 
            background: #1f2937; 
            color: #e5e7eb; 
            padding: 1rem; 
            border-radius: 4px; 
            overflow-x: auto;
        }}
        pre code {{ 
            background: none; 
            padding: 0; 
        }}
        ul {{ margin: 1rem 0; padding-left: 2rem; }}
        li {{ margin: 0.5rem 0; }}
        .nav {{ margin-bottom: 1rem; }}
        .nav a {{ color: #2563eb; text-decoration: none; margin-right: 1rem; }}
        .nav a:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="nav">
        <a href="/">← Dashboard</a>
        <a href="/docs">← Documentation Index</a>
    </div>
    <div class="doc-content">
        {html_content}
    </div>
</body>
</html>
'''
        return html
        
    except Exception as e:
        logger.error(f"Error serving doc {filename}: {e}")
        return jsonify({'error': str(e)}), 500

def get_system_stats():
    """Get system statistics"""
    stats = {
        'audio_files': count_files(AUDIO_DIR, '*.wav'),
        'transcripts': count_files(TRANSCRIPTS_DIR, '*.json'),
        'tasks': count_files(TASKS_DIR, '*.json'),
        'executions': count_files(Path('/app/data/executed'), '*.json') if Path('/app/data/executed').exists() else 0,
        'last_updated': datetime.now().isoformat(),
        'processing_status': 'unknown',
        'redis_available': redis_client is not None
    }
    
    # Get today's stats
    today = datetime.now().date()
    today_stats = {
        'audio': count_files_since(AUDIO_DIR, '*.wav', today),
        'transcripts': count_files_since(TRANSCRIPTS_DIR, '*.json', today),
        'tasks': count_files_since(TASKS_DIR, '*.json', today),
        'executions': count_files_since(Path('/app/data/executed'), '*.json', today) if Path('/app/data/executed').exists() else 0
    }
    stats['today'] = today_stats
    
    # Add processing statistics from Redis
    if redis_client:
        try:
            processing_keys = redis_client.keys('processing:*')
            stats['files_in_queue'] = len(processing_keys)
            
            # Count by status
            status_counts = {'pending': 0, 'processing': 0, 'completed': 0, 'failed': 0}
            for key in processing_keys:
                status = redis_client.hget(key, 'status')
                if status in status_counts:
                    status_counts[status] += 1
            
            stats['processing_breakdown'] = status_counts
            stats['processing_status'] = 'active' if status_counts['processing'] > 0 else 'idle'
            
        except Exception as e:
            logger.warning(f"Failed to get Redis stats: {e}")
            stats['processing_status'] = 'error'
    
    return stats

def count_files(directory, pattern):
    """Count files matching pattern in directory"""
    try:
        return len(list(directory.glob(pattern)))
    except:
        return 0

def count_files_since(directory, pattern, since_date):
    """Count files created since a specific date"""
    try:
        count = 0
        for file_path in directory.glob(pattern):
            file_date = datetime.fromtimestamp(file_path.stat().st_mtime).date()
            if file_date >= since_date:
                count += 1
        return count
    except:
        return 0

def list_files(directory, pattern):
    """List files matching pattern in directory"""
    try:
        files = []
        for file_path in directory.glob(pattern):
            stat = file_path.stat()
            files.append({
                'name': file_path.name,
                'path': str(file_path.relative_to(Path('/app/data'))),
                'size': stat.st_size,
                'modified': stat.st_mtime,
                'modified_iso': datetime.fromtimestamp(stat.st_mtime).isoformat()
            })
        
        # Sort by modification time (newest first)
        files.sort(key=lambda f: f['modified'], reverse=True)
        return files
    
    except Exception as e:
        logger.error(f"Error listing files in {directory}: {e}")
        return []

# WebSocket event handlers
@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    logger.info('Client connected')
    emit('connected', {'data': 'Connected to Mike Logger Dashboard'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logger.info('Client disconnected')

# Background task to monitor changes and emit updates
def monitor_updates():
    """Monitor file system for changes and emit updates"""
    last_stats = {}
    
    while True:
        try:
            # Get current stats
            current_stats = get_system_stats()
            
            # Check if stats changed
            if current_stats != last_stats:
                socketio.emit('stats_update', current_stats)
                last_stats = current_stats
            
            # Check for new activities
            # This is a simplified version - in production you'd want more sophisticated change detection
            time.sleep(5)
            
        except Exception as e:
            logger.error(f"Error in monitor thread: {e}")
            time.sleep(10)

# Start monitoring thread
monitor_thread = threading.Thread(target=monitor_updates)
monitor_thread.daemon = True
monitor_thread.start()

if __name__ == '__main__':
    # When running directly (not with gunicorn)
    socketio.run(app, host='0.0.0.0', port=8080, debug=True, allow_unsafe_werkzeug=True)