#!/usr/bin/env python3
"""
Mike Logger Dashboard - Web interface for monitoring
"""
import os
import json
import redis
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, render_template, jsonify, request
import logging
import tempfile
import shutil

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder='/app/templates')
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'dev-key-change-in-production')

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

@app.route('/')
def index():
    """Dashboard home page"""
    stats = get_system_stats()
    return render_template('dashboard.html', stats=stats)

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

def get_system_stats():
    """Get system statistics"""
    stats = {
        'audio_files': count_files(AUDIO_DIR, '*.wav'),
        'transcripts': count_files(TRANSCRIPTS_DIR, '*.json'),
        'tasks': count_files(TASKS_DIR, '*.json'),
        'last_updated': datetime.now().isoformat(),
        'processing_status': 'unknown',
        'redis_available': redis_client is not None
    }
    
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=os.getenv('FLASK_ENV') == 'development')