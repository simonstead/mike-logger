#!/usr/bin/env python3
"""
Quick script to execute approved tasks from Redis
"""
import redis
import json
import os

# Connect to Redis
redis_client = redis.from_url('redis://localhost:6380', decode_responses=True)

# Get approved tasks
approved_keys = redis_client.keys('approved_tasks:*')
print(f"Found {len(approved_keys)} approved tasks")

for key in approved_keys:
    task_data = redis_client.hgetall(key)
    if task_data:
        task = json.loads(task_data.get('task', '{}'))
        context = json.loads(task_data.get('context', '{}'))
        
        print(f"\nTask: {task.get('content', 'Unknown')}")
        print(f"Project: {context.get('project', 'Unknown')}")
        print(f"Working directory: {context.get('working_directory', 'Unknown')}")
        
        # For now, just show what would be executed
        print("\nThis task would be sent to Claude API for execution.")
        print("The executor container needs to be fixed to properly check for approved tasks.")