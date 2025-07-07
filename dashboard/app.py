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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
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