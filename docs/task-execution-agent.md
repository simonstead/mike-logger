# Mike Logger Task Execution Agent

## Overview

An autonomous agent that monitors extracted tasks and executes them using Claude Code, with proper filesystem access, MCP server integration, and project organization.

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Task Queue    │────▶│ Execution Agent  │────▶│  Claude Code    │
│ (./data/tasks/) │     │   (Orchestrator) │     │  (via CLI/API)  │
└─────────────────┘     └──────────────────┘     └─────────────────┘
         │                        │                         │
         │                        ▼                         ▼
         │              ┌──────────────────┐     ┌─────────────────┐
         │              │  Intent Analyzer  │     │   MCP Servers   │
         │              │  (Task Router)    │     │ (filesystem,    │
         │              └──────────────────┘     │  github, etc)   │
         │                        │               └─────────────────┘
         ▼                        ▼
┌─────────────────┐     ┌──────────────────┐
│  Redis Queue    │     │ Project Manager  │
│ (Status/State)  │     │ (Organizes work) │
└─────────────────┘     └──────────────────┘
```

## Core Components

### 1. Task Execution Agent (`src/task_executor.py`)

```python
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
from typing import Dict, Any, Optional
import redis
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logger = logging.getLogger(__name__)

class TaskExecutor:
    def __init__(self):
        self.tasks_dir = Path('/app/data/tasks')
        self.executed_dir = Path('/app/data/executed')
        self.projects_dir = Path('/app/projects')
        self.redis_client = self._init_redis()
        
        # Ensure directories exist
        for dir_path in [self.executed_dir, self.projects_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
    
    def _init_redis(self):
        """Initialize Redis connection"""
        try:
            redis_url = os.getenv('REDIS_URL', 'redis://redis:6379')
            client = redis.from_url(redis_url, decode_responses=True)
            client.ping()
            return client
        except Exception as e:
            logger.warning(f"Redis not available: {e}")
            return None
    
    def analyze_intent(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze task intent and determine execution strategy"""
        content = task.get('content', '')
        task_type = task.get('type', 'task')
        entities = task.get('entities', {})
        
        # Determine project context
        project = self._determine_project(content, entities)
        
        # Classify execution type
        execution_type = self._classify_execution(content, task_type)
        
        # Build execution context
        context = {
            'project': project,
            'execution_type': execution_type,
            'working_directory': self.projects_dir / project,
            'requires_mcp': self._requires_mcp(content),
            'sandbox_mode': self._is_risky(content),
            'approval_required': task.get('priority') == 'high'
        }
        
        return context
    
    def _determine_project(self, content: str, entities: Dict) -> str:
        """Determine which project this task belongs to"""
        # Look for project indicators
        lower_content = content.lower()
        
        # Check for explicit project mentions
        if 'mike logger' in lower_content or 'mike_logger' in lower_content:
            return 'mike_logger'
        
        # Check entities for topics that map to projects
        topic = entities.get('topic', '').lower()
        if 'readme' in topic or 'documentation' in topic:
            return 'docs'
        
        # Default to general project
        return 'general'
    
    def _classify_execution(self, content: str, task_type: str) -> str:
        """Classify the type of execution needed"""
        lower_content = content.lower()
        
        if any(word in lower_content for word in ['create', 'write', 'generate', 'build']):
            return 'create'
        elif any(word in lower_content for word in ['fix', 'debug', 'resolve', 'repair']):
            return 'fix'
        elif any(word in lower_content for word in ['update', 'modify', 'change', 'edit']):
            return 'update'
        elif any(word in lower_content for word in ['analyze', 'review', 'check', 'test']):
            return 'analyze'
        elif task_type == 'reminder':
            return 'remind'
        else:
            return 'general'
    
    def _requires_mcp(self, content: str) -> bool:
        """Determine if task requires MCP server access"""
        mcp_indicators = [
            'github', 'git', 'repository', 'commit', 'push',
            'database', 'api', 'server', 'deploy'
        ]
        return any(indicator in content.lower() for indicator in mcp_indicators)
    
    def _is_risky(self, content: str) -> bool:
        """Determine if task should run in sandbox mode"""
        risky_indicators = [
            'delete', 'remove', 'drop', 'truncate',
            'production', 'live', 'deploy', 'push'
        ]
        return any(indicator in content.lower() for indicator in risky_indicators)
    
    def execute_with_claude(self, task: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute task using Claude Code CLI"""
        try:
            # Prepare working directory
            work_dir = context['working_directory']
            work_dir.mkdir(parents=True, exist_ok=True)
            
            # Build Claude Code command
            cmd = self._build_claude_command(task, context)
            
            # Log execution start
            logger.info(f"Executing task with Claude Code: {task['content']}")
            self._update_status(task, 'executing', {'command': cmd})
            
            # Execute command
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                cwd=str(work_dir),
                timeout=300  # 5 minute timeout
            )
            
            # Process results
            execution_result = {
                'success': result.returncode == 0,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'return_code': result.returncode,
                'executed_at': datetime.now().isoformat(),
                'working_directory': str(work_dir)
            }
            
            # Update status
            status = 'completed' if execution_result['success'] else 'failed'
            self._update_status(task, status, execution_result)
            
            return execution_result
            
        except subprocess.TimeoutExpired:
            logger.error(f"Task execution timed out: {task['content']}")
            return {
                'success': False,
                'error': 'Execution timeout',
                'executed_at': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error executing task: {e}")
            return {
                'success': False,
                'error': str(e),
                'executed_at': datetime.now().isoformat()
            }
    
    def _build_claude_command(self, task: Dict[str, Any], context: Dict[str, Any]) -> str:
        """Build Claude Code CLI command"""
        base_cmd = "claude-code"
        
        # Add MCP servers if needed
        if context.get('requires_mcp'):
            base_cmd += " --mcp filesystem --mcp github"
        
        # Add sandbox mode if risky
        if context.get('sandbox_mode'):
            base_cmd += " --sandbox"
        
        # Build the prompt
        prompt = f'"{task["content"]}"'
        
        # Add context about the project
        if context['project'] != 'general':
            prompt = f'"In the {context["project"]} project: {task["content"]}"'
        
        return f'{base_cmd} {prompt}'
    
    def _update_status(self, task: Dict[str, Any], status: str, data: Dict[str, Any]):
        """Update task execution status in Redis"""
        if not self.redis_client:
            return
        
        try:
            key = f"execution:{task.get('id', 'unknown')}"
            self.redis_client.hset(key, mapping={
                'status': status,
                'updated_at': datetime.now().isoformat(),
                'task': json.dumps(task),
                'data': json.dumps(data)
            })
            self.redis_client.expire(key, 86400 * 7)  # Keep for 7 days
        except Exception as e:
            logger.warning(f"Failed to update Redis: {e}")
    
    def process_task_file(self, task_file: Path):
        """Process a single task file"""
        try:
            with open(task_file, 'r') as f:
                task_data = json.load(f)
            
            tasks = task_data.get('tasks', [])
            
            for task in tasks:
                # Add metadata
                task['id'] = f"{task_file.stem}_{tasks.index(task)}"
                task['source_file'] = str(task_file)
                
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
            
            # Move processed file
            self._archive_task_file(task_file)
            
        except Exception as e:
            logger.error(f"Error processing task file {task_file}: {e}")
    
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
        
        archive_path = archive_dir / task_file.name
        task_file.rename(archive_path)
        logger.info(f"Task file archived: {archive_path}")


class TaskFileHandler(FileSystemEventHandler):
    """Watch for new task files"""
    def __init__(self, executor: TaskExecutor):
        self.executor = executor
    
    def on_created(self, event):
        if event.is_directory:
            return
        
        if event.src_path.endswith('.json'):
            logger.info(f"New task file detected: {event.src_path}")
            time.sleep(1)  # Wait for file to be fully written
            self.executor.process_task_file(Path(event.src_path))


def main():
    """Main entry point"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    executor = TaskExecutor()
    
    # Process existing files
    existing_files = list(executor.tasks_dir.glob('*.json'))
    for task_file in existing_files:
        if not task_file.name.startswith('.'):
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
        observer.stop()
    observer.join()


if __name__ == '__main__':
    main()
```

### 2. Project Organization Strategy

```yaml
# Project structure
projects/
├── mike_logger/          # Mike Logger related tasks
│   ├── features/         # New feature implementations
│   ├── bugs/            # Bug fixes
│   └── docs/            # Documentation updates
├── general/             # General tasks
│   ├── notes/           # Quick notes and ideas
│   ├── reminders/       # Time-based reminders
│   └── misc/            # Miscellaneous tasks
├── work/                # Work-related tasks
│   ├── meetings/        # Meeting notes and actions
│   ├── projects/        # Specific work projects
│   └── reports/         # Reports and analysis
└── personal/            # Personal tasks
    ├── shopping/        # Shopping lists
    ├── health/          # Health reminders
    └── finance/         # Financial tasks
```

### 3. MCP Server Integration

```python
# MCP configuration for task executor
MCP_SERVERS = {
    'filesystem': {
        'command': 'mcp-server-filesystem',
        'args': ['--root', '/app/projects'],
        'required_for': ['create', 'update', 'fix']
    },
    'github': {
        'command': 'mcp-server-github',
        'env': {'GITHUB_TOKEN': os.getenv('GITHUB_TOKEN')},
        'required_for': ['commit', 'push', 'pr']
    },
    'sqlite': {
        'command': 'mcp-server-sqlite',
        'args': ['--db', '/app/data/tasks.db'],
        'required_for': ['analyze', 'report']
    }
}
```

### 4. Intent Classification Rules

```python
INTENT_RULES = {
    'create_file': {
        'patterns': ['create', 'write', 'generate', 'make'],
        'entities': ['file', 'document', 'script', 'code'],
        'mcp_servers': ['filesystem'],
        'template': 'Create a new {entity} with the following content: {content}'
    },
    'fix_bug': {
        'patterns': ['fix', 'debug', 'resolve', 'repair'],
        'entities': ['bug', 'error', 'issue', 'problem'],
        'mcp_servers': ['filesystem', 'github'],
        'template': 'Fix the following issue: {content}'
    },
    'update_code': {
        'patterns': ['update', 'modify', 'change', 'refactor'],
        'entities': ['code', 'function', 'class', 'module'],
        'mcp_servers': ['filesystem'],
        'template': 'Update the code as follows: {content}'
    },
    'create_reminder': {
        'patterns': ['remind', 'remember', 'don\'t forget'],
        'entities': ['tomorrow', 'later', 'meeting', 'call'],
        'mcp_servers': [],
        'template': 'Set a reminder: {content}'
    }
}
```

### 5. Approval System for High-Risk Tasks

```python
# Web interface for approvals (add to dashboard)
@app.route('/api/approvals')
def get_pending_approvals():
    """Get tasks pending approval"""
    if not redis_client:
        return jsonify([])
    
    approval_keys = redis_client.keys('approval_queue:*')
    approvals = []
    
    for key in approval_keys:
        data = redis_client.hgetall(key)
        approvals.append({
            'id': key.replace('approval_queue:', ''),
            'task': json.loads(data.get('task', '{}')),
            'context': json.loads(data.get('context', '{}')),
            'queued_at': data.get('queued_at')
        })
    
    return jsonify(approvals)

@app.route('/api/approvals/<approval_id>', methods=['POST'])
def approve_task(approval_id):
    """Approve or reject a task"""
    action = request.json.get('action')  # 'approve' or 'reject'
    
    if action == 'approve':
        # Move to execution queue
        # ... implementation
        pass
    
    return jsonify({'success': True})
```

## Docker Service Configuration

```yaml
# Add to docker-compose.yml
task-executor:
  build:
    context: .
    dockerfile: Dockerfile.executor
  container_name: mike-logger-executor
  environment:
    - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    - GITHUB_TOKEN=${GITHUB_TOKEN}
    - CLAUDE_CODE_PATH=/usr/local/bin/claude-code
    - REDIS_URL=redis://redis:6379
  volumes:
    - ./data:/app/data
    - ./projects:/app/projects
    - ./logs:/app/logs
    # Mount claude-code binary
    - /usr/local/bin/claude-code:/usr/local/bin/claude-code:ro
    # Mount MCP server configs
    - ./config/mcp:/app/.config/mcp
  depends_on:
    - redis
    - processor
  restart: unless-stopped
```

## Security Considerations

1. **Sandboxing**: Run risky operations in isolated environments
2. **Approval Queue**: High-priority or risky tasks require manual approval
3. **Project Isolation**: Each project has its own workspace
4. **Audit Trail**: All executions are logged with full context
5. **Rate Limiting**: Prevent runaway execution loops

## Example Task Flows

### 1. Simple File Creation
```
User: "Create a README file for my new project"
→ Task extracted with type='create', entities={action:'create', topic:'readme file'}
→ Intent: create_file in project='general'
→ Execute: claude-code "Create a README.md file for a new project"
→ Result saved to projects/general/README.md
```

### 2. Bug Fix with Approval
```
User: "Fix the production bug in the payment system"
→ Task extracted with priority='high', entities={action:'fix', topic:'payment system'}
→ Intent: fix_bug, risky=true, approval_required=true
→ Queued for approval with full context
→ Admin approves via dashboard
→ Execute with sandbox mode and monitoring
```

### 3. Scheduled Reminder
```
User: "Remind me to review the quarterly report tomorrow"
→ Task extracted with type='reminder', deadline='tomorrow'
→ Intent: create_reminder
→ Scheduled in task queue for tomorrow
→ Notification sent at scheduled time
```

## Monitoring Dashboard Updates

Add to the dashboard:
- Execution status view
- Approval queue interface
- Project file browser
- Execution history with filters
- Success/failure metrics

## Next Steps

1. Implement the task executor service
2. Add Claude Code CLI integration
3. Create approval interface in dashboard
4. Set up MCP server configurations
5. Add project templates and scaffolding
6. Implement notification system for completed tasks