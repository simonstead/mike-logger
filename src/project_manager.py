#!/usr/bin/env python3
"""
Mike Logger Project Manager
Intelligent project detection and creation
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import re
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

class ProjectManager:
    def __init__(self, projects_dir: Path):
        self.projects_dir = projects_dir
        self.projects_cache = {}
        self.project_metadata_file = projects_dir / '.project_metadata.json'
        self._load_project_metadata()
    
    def _load_project_metadata(self):
        """Load metadata about existing projects"""
        if self.project_metadata_file.exists():
            with open(self.project_metadata_file, 'r') as f:
                self.projects_cache = json.load(f)
        else:
            self._scan_existing_projects()
    
    def _scan_existing_projects(self):
        """Scan existing projects and build metadata"""
        for project_dir in self.projects_dir.iterdir():
            if project_dir.is_dir() and not project_dir.name.startswith('.'):
                self.projects_cache[project_dir.name] = {
                    'created_at': datetime.fromtimestamp(project_dir.stat().st_ctime).isoformat(),
                    'keywords': self._extract_project_keywords(project_dir),
                    'description': self._extract_project_description(project_dir),
                    'file_count': sum(1 for _ in project_dir.rglob('*') if _.is_file()),
                    'last_modified': datetime.fromtimestamp(project_dir.stat().st_mtime).isoformat()
                }
        self._save_project_metadata()
    
    def _extract_project_keywords(self, project_dir: Path) -> List[str]:
        """Extract keywords from project files"""
        keywords = set()
        
        # Add project name parts
        name_parts = re.split(r'[-_\s]+', project_dir.name.lower())
        keywords.update(name_parts)
        
        # Check for README or other descriptive files
        for readme in project_dir.glob('README*'):
            if readme.is_file():
                try:
                    content = readme.read_text()[:500].lower()  # First 500 chars
                    # Extract meaningful words
                    words = re.findall(r'\b[a-z]{3,}\b', content)
                    keywords.update(words[:20])  # Top 20 words
                except:
                    pass
        
        # Check package.json, requirements.txt, etc for tech stack
        tech_files = {
            'package.json': ['node', 'javascript', 'npm'],
            'requirements.txt': ['python', 'pip'],
            'Gemfile': ['ruby', 'gem'],
            'Cargo.toml': ['rust', 'cargo'],
            'pom.xml': ['java', 'maven'],
            'build.gradle': ['java', 'gradle'],
            'docker-compose.yml': ['docker', 'container'],
            'Dockerfile': ['docker', 'container']
        }
        
        for tech_file, tech_keywords in tech_files.items():
            if (project_dir / tech_file).exists():
                keywords.update(tech_keywords)
        
        return list(keywords)
    
    def _extract_project_description(self, project_dir: Path) -> str:
        """Extract project description from README or similar"""
        for readme in project_dir.glob('README*'):
            if readme.is_file():
                try:
                    content = readme.read_text()
                    # Extract first paragraph or description
                    lines = content.split('\n')
                    for i, line in enumerate(lines):
                        if line.strip() and not line.startswith('#'):
                            return line.strip()[:200]
                except:
                    pass
        return ""
    
    def _save_project_metadata(self):
        """Save project metadata to file"""
        with open(self.project_metadata_file, 'w') as f:
            json.dump(self.projects_cache, f, indent=2)
    
    def determine_project(self, task_content: str, entities: Dict, 
                         confidence_threshold: float = 0.7) -> Tuple[str, bool, float]:
        """
        Determine which project a task belongs to
        
        Returns:
            tuple: (project_name, is_new_project, confidence_score)
        """
        # Extract keywords from task
        task_keywords = self._extract_task_keywords(task_content, entities)
        
        # Check for explicit project mentions
        explicit_project = self._check_explicit_project_mention(task_content)
        if explicit_project:
            return explicit_project, False, 1.0
        
        # Check for new project indicators
        if self._is_new_project_request(task_content):
            project_name = self._generate_project_name(task_content, entities)
            return project_name, True, 0.9
        
        # Find best matching existing project
        best_match, confidence = self._find_best_project_match(task_keywords, task_content)
        
        if confidence >= confidence_threshold:
            return best_match, False, confidence
        
        # Check if task suggests a new domain/project
        if self._suggests_new_domain(task_keywords, task_content):
            project_name = self._generate_project_name(task_content, entities)
            return project_name, True, 0.8
        
        # Default to general if low confidence
        return 'general', False, confidence
    
    def _extract_task_keywords(self, content: str, entities: Dict) -> List[str]:
        """Extract keywords from task content"""
        keywords = []
        
        # Add entity topics
        if 'topic' in entities:
            keywords.extend(entities['topic'].lower().split())
        
        # Extract meaningful words from content
        words = re.findall(r'\b[a-z]{3,}\b', content.lower())
        
        # Filter out common words
        stop_words = {'the', 'and', 'for', 'with', 'this', 'that', 'from', 'into', 'can', 'will'}
        keywords.extend([w for w in words if w not in stop_words])
        
        return keywords
    
    def _check_explicit_project_mention(self, content: str) -> Optional[str]:
        """Check if task explicitly mentions a project"""
        content_lower = content.lower()
        
        # Check for "for the X project" or "in the X project"
        patterns = [
            r'for the (\w+) project',
            r'in the (\w+) project',
            r'to the (\w+) project',
            r'(\w+) project:',
            r'project[:\s]+(\w+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, content_lower)
            if match:
                project_name = match.group(1)
                # Check if this project exists
                if project_name in self.projects_cache:
                    return project_name
                # Check for similar names
                for existing in self.projects_cache:
                    if SequenceMatcher(None, project_name, existing).ratio() > 0.8:
                        return existing
        
        return None
    
    def _is_new_project_request(self, content: str) -> bool:
        """Check if task is requesting a new project"""
        new_project_indicators = [
            'create a new project',
            'start a new project',
            'initialize a project',
            'new project called',
            'new project named',
            'create project',
            'start project',
            'begin a project',
            'set up a project'
        ]
        
        content_lower = content.lower()
        return any(indicator in content_lower for indicator in new_project_indicators)
    
    def _find_best_project_match(self, task_keywords: List[str], content: str) -> Tuple[str, float]:
        """Find the best matching existing project"""
        scores = {}
        
        for project_name, metadata in self.projects_cache.items():
            score = 0.0
            project_keywords = metadata.get('keywords', [])
            
            # Keyword matching
            for keyword in task_keywords:
                if keyword in project_keywords:
                    score += 1.0
                # Partial matching
                for proj_keyword in project_keywords:
                    if keyword in proj_keyword or proj_keyword in keyword:
                        score += 0.5
            
            # Name similarity
            name_similarity = SequenceMatcher(None, 
                                            ' '.join(task_keywords), 
                                            project_name.replace('_', ' ')).ratio()
            score += name_similarity * 3  # Weight name similarity higher
            
            # Description matching
            if metadata.get('description'):
                desc_similarity = SequenceMatcher(None, 
                                                content.lower(), 
                                                metadata['description'].lower()).ratio()
                score += desc_similarity * 2
            
            # Normalize score
            max_possible = len(task_keywords) + 5  # keyword matches + weighted similarities
            normalized_score = min(score / max_possible, 1.0)
            scores[project_name] = normalized_score
        
        if not scores:
            return 'general', 0.0
        
        best_project = max(scores, key=scores.get)
        return best_project, scores[best_project]
    
    def _suggests_new_domain(self, keywords: List[str], content: str) -> bool:
        """Check if task suggests a completely new domain"""
        # Check against all existing project keywords
        all_existing_keywords = set()
        for metadata in self.projects_cache.values():
            all_existing_keywords.update(metadata.get('keywords', []))
        
        # Count how many keywords are new
        new_keywords = [k for k in keywords if k not in all_existing_keywords]
        
        # If more than 60% of keywords are new, might be new domain
        if len(keywords) > 0 and len(new_keywords) / len(keywords) > 0.6:
            return True
        
        # Check for domain-specific terms that suggest new project
        domain_indicators = {
            'game': ['game', 'player', 'score', 'level'],
            'api': ['api', 'endpoint', 'rest', 'graphql'],
            'ml': ['machine learning', 'neural', 'model', 'training'],
            'web': ['website', 'webpage', 'frontend', 'backend'],
            'mobile': ['mobile', 'app', 'ios', 'android'],
            'data': ['database', 'analytics', 'etl', 'pipeline'],
            'cli': ['cli', 'command line', 'terminal', 'bash'],
            'bot': ['bot', 'automation', 'discord', 'telegram']
        }
        
        content_lower = content.lower()
        for domain, indicators in domain_indicators.items():
            if any(ind in content_lower for ind in indicators):
                # Check if we already have a project for this domain
                domain_exists = any(domain in proj.lower() for proj in self.projects_cache)
                if not domain_exists:
                    return True
        
        return False
    
    def _generate_project_name(self, content: str, entities: Dict) -> str:
        """Generate a project name from task content"""
        # Try to extract name from content
        patterns = [
            r'project (?:called|named) ["\']?(\w+)["\']?',
            r'["\'](\w+)["\'] project',
            r'create (?:a )?(\w+)',
            r'build (?:a )?(\w+)',
        ]
        
        content_lower = content.lower()
        for pattern in patterns:
            match = re.search(pattern, content_lower)
            if match:
                name = match.group(1)
                if len(name) > 2:  # Reasonable length
                    return name.lower().replace(' ', '_')
        
        # Generate from entities
        if 'topic' in entities:
            topic_words = entities['topic'].lower().split()
            # Filter out generic words
            meaningful = [w for w in topic_words if len(w) > 3 and w not in 
                         {'with', 'from', 'that', 'this', 'have', 'make', 'create'}]
            if meaningful:
                return '_'.join(meaningful[:2])  # Use first 2 meaningful words
        
        # Last resort: generate from action + timestamp
        timestamp = datetime.now().strftime("%Y%m%d")
        return f"project_{timestamp}"
    
    def create_project(self, project_name: str, description: str = "", 
                      keywords: List[str] = None) -> Path:
        """Create a new project directory and update metadata"""
        project_dir = self.projects_dir / project_name
        project_dir.mkdir(exist_ok=True)
        
        # Update metadata
        self.projects_cache[project_name] = {
            'created_at': datetime.now().isoformat(),
            'keywords': keywords or [],
            'description': description,
            'file_count': 0,
            'last_modified': datetime.now().isoformat()
        }
        
        # Create README
        readme_path = project_dir / 'README.md'
        if not readme_path.exists():
            readme_content = f"""# {project_name.replace('_', ' ').title()}

{description if description else 'Project created by Mike Logger task executor.'}

## Overview
This project was automatically created based on voice commands.

## Created
{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
            readme_path.write_text(readme_content)
        
        self._save_project_metadata()
        logger.info(f"Created new project: {project_name}")
        
        return project_dir