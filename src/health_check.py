#!/usr/bin/env python3
"""
Health check script for Docker containers
"""
import sys
import requests
import redis
import os

def check_processor_health():
    """Check if processor is healthy"""
    try:
        # Check metrics endpoint
        response = requests.get('http://localhost:8000/metrics', timeout=5)
        if response.status_code == 200:
            return True
    except:
        pass
    return False

def check_redis_health():
    """Check if Redis is healthy"""
    try:
        redis_url = os.getenv('REDIS_URL', 'redis://redis:6379')
        client = redis.from_url(redis_url)
        client.ping()
        return True
    except:
        return False

def main():
    """Main health check"""
    service_type = os.getenv('SERVICE_TYPE', 'processor')
    
    if service_type == 'processor':
        healthy = check_processor_health()
    elif service_type == 'redis':
        healthy = check_redis_health()
    else:
        healthy = False
    
    if healthy:
        print("OK")
        sys.exit(0)
    else:
        print("UNHEALTHY")
        sys.exit(1)

if __name__ == '__main__':
    main()