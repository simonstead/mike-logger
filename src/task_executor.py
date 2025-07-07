#!/usr/bin/env python3
"""
Mike Logger Task Execution Agent
Monitors task queue and executes using Claude Code
"""

import os
import json
import time
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
import redis
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import requests
import sys
sys.path.append('/app')
from src.project_manager import ProjectManager

# Configure logging
logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TaskExecutor:
    def __init__(self):
        self.tasks_dir = Path('/app/data/tasks')
        self.executed_dir = Path('/app/data/executed')
        self.projects_dir = Path('/app/projects')
        self.redis_client = self._init_redis()
        self.anthropic_api_key = self._init_anthropic()
        
        # Ensure directories exist
        for dir_path in [self.executed_dir, self.projects_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize project manager
        self.project_manager = ProjectManager(self.projects_dir)
    
    def _init_redis(self) -> Optional[redis.Redis]:
        """Initialize Redis connection"""
        try:
            redis_url = os.getenv('REDIS_URL', 'redis://redis:6379')
            client = redis.from_url(redis_url, decode_responses=True)
            client.ping()
            logger.info("Redis connection established")
            return client
        except Exception as e:
            logger.warning(f"Redis not available: {e}")
            return None
    
    def _init_anthropic(self) -> Optional[str]:
        """Initialize Anthropic API key"""
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            logger.error("ANTHROPIC_API_KEY not set")
            return None
        
        logger.info("Anthropic API key loaded")
        return api_key
    
    def analyze_intent(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze task intent and determine execution strategy"""
        content = task.get('content', '')
        task_type = task.get('type', 'task')
        entities = task.get('entities', {})
        priority = task.get('priority', 'medium')
        
        # Use project manager to determine project
        project_name, is_new_project, confidence = self.project_manager.determine_project(
            content, entities
        )
        
        # Create new project if needed
        if is_new_project:
            logger.info(f"Creating new project: {project_name} (confidence: {confidence:.2f})")
            description = f"Project for: {content[:100]}..."
            keywords = entities.get('topic', '').split() if 'topic' in entities else []
            self.project_manager.create_project(project_name, description, keywords)
        else:
            logger.info(f"Using existing project: {project_name} (confidence: {confidence:.2f})")
        
        # Classify execution type
        execution_type = self._classify_execution(content, task_type)
        
        # Build execution context
        context = {
            'project': project_name,
            'is_new_project': is_new_project,
            'project_confidence': confidence,
            'execution_type': execution_type,
            'working_directory': str(self.projects_dir / project_name),
            'requires_mcp': self._requires_mcp(content),
            'sandbox_mode': self._is_risky(content),
            'approval_required': priority == 'high' or self._is_risky(content),
            'priority': priority
        }
        
        logger.info(f"Task intent analyzed: {execution_type} in project '{project_name}'")
        return context
    
    def _determine_project(self, content: str, entities: Dict) -> str:
        """Determine which project this task belongs to"""
        lower_content = content.lower()
        
        # Check for explicit project mentions
        project_mappings = {
            'mike_logger': ['mike logger', 'mike_logger', 'this project', 'current project'],
            'docs': ['readme', 'documentation', 'docs', 'guide'],
            'work': ['meeting', 'report', 'presentation', 'client'],
            'personal': ['buy', 'shopping', 'reminder', 'appointment', 'call']
        }
        
        for project, keywords in project_mappings.items():
            if any(keyword in lower_content for keyword in keywords):
                return project
        
        # Check entities for topics
        topic = entities.get('topic', '').lower()
        for project, keywords in project_mappings.items():
            if any(keyword in topic for keyword in keywords):
                return project
        
        # Default to general project
        return 'general'
    
    def _classify_execution(self, content: str, task_type: str) -> str:
        """Classify the type of execution needed"""
        lower_content = content.lower()
        
        execution_mappings = [
            (['create', 'write', 'generate', 'build', 'make', 'add'], 'create'),
            (['fix', 'debug', 'resolve', 'repair', 'solve'], 'fix'),
            (['update', 'modify', 'change', 'edit', 'refactor'], 'update'),
            (['analyze', 'review', 'check', 'test', 'inspect'], 'analyze'),
            (['delete', 'remove', 'clean', 'clear'], 'delete'),
            (['remind', 'remember', "don't forget"], 'remind')
        ]
        
        for keywords, exec_type in execution_mappings:
            if any(keyword in lower_content for keyword in keywords):
                return exec_type
        
        if task_type == 'reminder':
            return 'remind'
        elif task_type == 'idea':
            return 'note'
        
        return 'general'
    
    def _requires_mcp(self, content: str) -> List[str]:
        """Determine which MCP servers are needed"""
        lower_content = content.lower()
        required_servers = []
        
        # Filesystem is almost always needed
        if any(word in lower_content for word in ['file', 'create', 'write', 'read', 'edit']):
            required_servers.append('filesystem')
        
        # GitHub operations
        if any(word in lower_content for word in ['github', 'git', 'commit', 'push', 'repository']):
            required_servers.append('github')
        
        # Database operations
        if any(word in lower_content for word in ['database', 'query', 'sql', 'data']):
            required_servers.append('sqlite')
        
        return required_servers
    
    def _is_risky(self, content: str) -> bool:
        """Determine if task should run in sandbox mode"""
        risky_indicators = [
            'delete', 'remove', 'drop', 'truncate', 'destroy',
            'production', 'live', 'deploy', 'push to main',
            'sudo', 'admin', 'root', 'system'
        ]
        return any(indicator in content.lower() for indicator in risky_indicators)
    
    def execute_with_claude(self, task: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute task using Claude Code CLI or simulation"""
        try:
            # Prepare working directory
            work_dir = Path(context['working_directory'])
            work_dir.mkdir(parents=True, exist_ok=True)
            
            # Log execution start
            logger.info(f"Executing task: {task['content']}")
            self._update_status(task, 'executing', {'context': context})
            
            if self.anthropic_api_key:
                # Execute with Claude API
                result = self._execute_with_claude_api(task, context, work_dir)
            else:
                # Fallback to simulation
                logger.warning("No Anthropic API key available, simulating execution")
                result = self._simulate_execution(task, context, work_dir)
            
            # Update status
            status = 'completed' if result['success'] else 'failed'
            self._update_status(task, status, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Error executing task: {e}")
            error_result = {
                'success': False,
                'error': str(e),
                'executed_at': datetime.now().isoformat()
            }
            self._update_status(task, 'failed', error_result)
            return error_result
    
    def _execute_with_claude_api(self, task: Dict[str, Any], context: Dict[str, Any], work_dir: Path) -> Dict[str, Any]:
        """Execute task using Claude API directly"""
        try:
            # Build enhanced prompt based on execution type
            prompt = self._build_execution_prompt(task, context, work_dir)
            
            logger.info(f"Sending task to Claude API: {task['content']}")
            
            # Call Claude API using requests
            headers = {
                'anthropic-version': '2023-06-01',
                'x-api-key': self.anthropic_api_key,
                'content-type': 'application/json'
            }
            
            data = {
                'model': 'claude-3-haiku-20240307',  # Using Haiku for task execution
                'max_tokens': 4000,
                'temperature': 0.2,
                'messages': [{
                    'role': 'user',
                    'content': prompt
                }]
            }
            
            response = requests.post(
                'https://api.anthropic.com/v1/messages',
                headers=headers,
                json=data
            )
            
            if response.status_code != 200:
                raise Exception(f"API error: {response.status_code} - {response.text}")
            
            # Extract response
            response_json = response.json()
            response_text = response_json['content'][0]['text'] if response_json.get('content') else ""
            
            # Parse and execute any code from the response
            execution_result = self._parse_and_execute_response(response_text, work_dir, context)
            
            return {
                'success': execution_result['success'],
                'response': response_text,
                'files_created': execution_result.get('files_created', []),
                'files_modified': execution_result.get('files_modified', []),
                'executed_at': datetime.now().isoformat(),
                'working_directory': str(work_dir),
                'execution_type': context['execution_type']
            }
            
        except Exception as e:
            logger.error(f"Error executing with Claude API: {e}")
            return {
                'success': False,
                'error': str(e),
                'executed_at': datetime.now().isoformat(),
                'working_directory': str(work_dir)
            }
    
    def _build_execution_prompt(self, task: Dict[str, Any], context: Dict[str, Any], work_dir: Path) -> str:
        """Build detailed prompt for Claude based on execution type"""
        execution_type = context['execution_type']
        
        base_prompt = f"""You are an AI assistant helping to execute a task extracted from voice commands.

Task: {task['content']}
Task Type: {task.get('type', 'task')}
Priority: {task.get('priority', 'medium')}
Confidence: {task.get('confidence', 1.0)}

Working Directory: {work_dir}
Project Context: {context['project']}

Please execute this task by:
"""
        
        if execution_type == 'create':
            base_prompt += """
1. Creating the requested file(s) in the working directory
2. Return the complete file content in a code block with the filename as a comment
3. Make the content informative and well-structured
4. Follow best practices for the file type

Format your response as:
```filename.ext
file content here
```
"""
        elif execution_type == 'update':
            base_prompt += """
1. Describe what changes would be made
2. Provide the updated content in code blocks
3. Explain the modifications made
"""
        elif execution_type == 'analyze':
            base_prompt += """
1. Analyze the request
2. Provide insights and recommendations
3. Include any relevant code or examples
"""
        elif execution_type == 'remind':
            base_prompt += """
1. Create a reminder note with the details
2. Include the deadline if mentioned
3. Format it clearly for future reference
"""
        else:
            base_prompt += """
1. Understand and execute the task appropriately
2. Provide any created content in code blocks
3. Explain what was done
"""
        
        return base_prompt
    
    def _parse_and_execute_response(self, response: str, work_dir: Path, context: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Claude's response and execute any file operations"""
        result = {
            'success': True,
            'files_created': [],
            'files_modified': []
        }
        
        try:
            # Extract code blocks with filenames
            import re
            # First try to find code blocks with filenames
            code_blocks = re.findall(r'```(\S+)\n(.*?)```', response, re.DOTALL)
            
            for filename, content in code_blocks:
                # Skip language identifiers that aren't filenames (but not if they have extensions)
                if '.' not in filename and filename in ['python', 'javascript', 'bash', 'json', 'yaml', 'markdown', 'sh', 'py', 'js']:
                    continue
                
                # Create file in working directory
                file_path = work_dir / filename
                file_path.parent.mkdir(parents=True, exist_ok=True)
                
                file_path.write_text(content.strip())
                result['files_created'].append(str(file_path))
                logger.info(f"Created file: {file_path}")
            
            # If no code blocks but it's a create task, try to extract content
            if not code_blocks and context['execution_type'] == 'create':
                # Look for any formatted content
                if '# ' in response:  # Likely markdown
                    filename = 'README.md'
                    file_path = work_dir / filename
                    file_path.write_text(response.strip())
                    result['files_created'].append(str(file_path))
                    logger.info(f"Created file from response: {file_path}")
            
        except Exception as e:
            logger.error(f"Error parsing/executing response: {e}")
            result['success'] = False
            result['error'] = str(e)
        
        return result
    
    def _simulate_execution(self, task: Dict[str, Any], context: Dict[str, Any], work_dir: Path) -> Dict[str, Any]:
        """Simulate execution for testing without Claude Code"""
        logger.info(f"SIMULATION: Would execute task in {work_dir}")
        
        # Create example outputs based on execution type
        execution_type = context['execution_type']
        
        if execution_type == 'create':
            # Simulate file creation
            if 'readme' in task['content'].lower():
                file_path = work_dir / 'README.md'
                file_content = f"""# {context['project'].title()} Project

This README was created by Mike Logger Task Executor.

Task: {task['content']}
Created: {datetime.now().isoformat()}

## Overview
This is an automatically generated README file based on your voice command.

## Task Details
- Type: {task.get('type', 'task')}
- Priority: {task.get('priority', 'medium')}
- Confidence: {task.get('confidence', 0.0)}
"""
                file_path.write_text(file_content)
                message = f"Created {file_path}"
            else:
                message = f"Would create file based on: {task['content']}"
        
        elif execution_type == 'remind':
            message = f"Reminder set: {task['content']}"
        
        elif execution_type == 'analyze':
            message = f"Analysis complete for: {task['content']}"
        
        else:
            message = f"Task processed: {task['content']}"
        
        return {
            'success': True,
            'stdout': message,
            'stderr': '',
            'return_code': 0,
            'executed_at': datetime.now().isoformat(),
            'working_directory': str(work_dir),
            'command': 'SIMULATED',
            'simulation': True
        }
    
    def _update_status(self, task: Dict[str, Any], status: str, data: Dict[str, Any]):
        """Update task execution status in Redis"""
        if not self.redis_client:
            return
        
        try:
            task_id = task.get('id', f"task_{int(time.time())}")
            key = f"execution:{task_id}"
            
            self.redis_client.hset(key, mapping={
                'status': status,
                'updated_at': datetime.now().isoformat(),
                'task': json.dumps(task),
                'data': json.dumps(data)
            })
            self.redis_client.expire(key, 86400 * 7)  # Keep for 7 days
            
            # Also update in a list for easy retrieval
            self.redis_client.lpush('execution_history', key)
            self.redis_client.ltrim('execution_history', 0, 999)  # Keep last 1000
            
        except Exception as e:
            logger.warning(f"Failed to update Redis: {e}")
    
    def process_task_file(self, task_file: Path):
        """Process a single task file"""
        try:
            logger.info(f"Processing task file: {task_file}")
            
            with open(task_file, 'r') as f:
                task_data = json.load(f)
            
            tasks = task_data.get('tasks', [])
            source_transcript = task_data.get('source_transcript', '')
            
            for idx, task in enumerate(tasks):
                # Add metadata
                task['id'] = f"{task_file.stem}_{idx}"
                task['source_file'] = str(task_file)
                task['source_transcript'] = source_transcript
                
                # Skip low confidence tasks
                if task.get('confidence', 1.0) < 0.5:
                    logger.info(f"Skipping low confidence task: {task['content']}")
                    continue
                
                # Analyze intent
                context = self.analyze_intent(task)
                
                # Check if approval needed
                if context.get('approval_required'):
                    logger.info(f"Task requires approval: {task['content']}")
                    self._queue_for_approval(task, context)
                    continue
                
                # Execute task
                result = self.execute_with_claude(task, context)
                
                # Save execution result
                self._save_execution_result(task, context, result)
            
            # Move processed file to archive
            self._archive_task_file(task_file)
            
        except Exception as e:
            logger.error(f"Error processing task file {task_file}: {e}", exc_info=True)
    
    def _queue_for_approval(self, task: Dict[str, Any], context: Dict[str, Any]):
        """Queue high-priority tasks for manual approval"""
        if self.redis_client:
            approval_key = f"approval_queue:{task['id']}"
            self.redis_client.hset(approval_key, mapping={
                'task': json.dumps(task),
                'context': json.dumps(context),
                'queued_at': datetime.now().isoformat()
            })
            self.redis_client.expire(approval_key, 86400)  # 24 hours to approve
            logger.info(f"Task queued for approval: {approval_key}")
    
    def _save_execution_result(self, task: Dict[str, Any], context: Dict[str, Any], result: Dict[str, Any]):
        """Save execution results"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = self.executed_dir / f"execution_{timestamp}_{task['id']}.json"
        
        execution_data = {
            'task': task,
            'context': context,
            'result': result,
            'saved_at': datetime.now().isoformat()
        }
        
        with open(result_file, 'w') as f:
            json.dump(execution_data, f, indent=2)
        
        logger.info(f"Execution result saved: {result_file}")
    
    def _archive_task_file(self, task_file: Path):
        """Move processed task file to archive"""
        archive_dir = self.tasks_dir / 'processed'
        archive_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_path = archive_dir / f"{timestamp}_{task_file.name}"
        
        task_file.rename(archive_path)
        logger.info(f"Task file archived: {archive_path}")


class TaskFileHandler(FileSystemEventHandler):
    """Watch for new task files"""
    def __init__(self, executor: TaskExecutor):
        self.executor = executor
        self.processing = set()  # Track files being processed
    
    def on_created(self, event):
        if event.is_directory:
            return
        
        file_path = Path(event.src_path)
        
        # Only process JSON files not in subdirectories
        if file_path.suffix == '.json' and file_path.parent == self.executor.tasks_dir:
            # Skip if already processing
            if str(file_path) in self.processing:
                return
            
            # Skip hidden files and processed directory
            if file_path.name.startswith('.') or 'processed' in file_path.parts:
                return
            
            logger.info(f"New task file detected: {file_path}")
            self.processing.add(str(file_path))
            
            # Wait for file to be fully written
            time.sleep(1)
            
            try:
                self.executor.process_task_file(file_path)
            finally:
                self.processing.discard(str(file_path))


def main():
    """Main entry point"""
    logger.info("Starting Mike Logger Task Execution Agent")
    
    executor = TaskExecutor()
    
    # Process existing files first
    existing_files = list(executor.tasks_dir.glob('*.json'))
    logger.info(f"Found {len(existing_files)} existing task files")
    
    for task_file in existing_files:
        if not task_file.name.startswith('.') and task_file.is_file():
            executor.process_task_file(task_file)
    
    # Watch for new files
    event_handler = TaskFileHandler(executor)
    observer = Observer()
    observer.schedule(event_handler, str(executor.tasks_dir), recursive=False)
    observer.start()
    
    logger.info("Task Execution Agent started. Watching for new tasks...")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down Task Execution Agent")
        observer.stop()
    
    observer.join()
    logger.info("Task Execution Agent stopped")


if __name__ == '__main__':
    main()