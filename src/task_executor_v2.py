#!/usr/bin/env python3
"""
Enhanced Task Executor with Intelligent Context Awareness
"""
import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import hashlib
from datetime import datetime
import time

logger = logging.getLogger(__name__)

class ContextAnalyzer:
    """Analyzes project context to provide relevant information to Claude"""
    
    IMPORTANT_FILES = {
        'readme': ['README.md', 'readme.md', 'README.txt', 'readme.txt'],
        'package': ['package.json', 'requirements.txt', 'Cargo.toml', 'go.mod', 
                   'pom.xml', 'build.gradle', 'Gemfile', 'setup.py'],
        'config': ['.env', 'config.json', 'config.yaml', 'settings.py', 
                  'tsconfig.json', '.gitignore'],
        'main': ['main.py', 'index.js', 'app.py', 'server.js', 'main.go', 
                'index.html', 'App.js', 'main.rs'],
        'tests': ['test_*.py', '*.test.js', '*.spec.js', '*_test.go'],
        'docs': ['docs/', 'documentation/', 'wiki/']
    }
    
    MAX_FILE_SIZE = 50000  # 50KB max per file
    MAX_CONTEXT_SIZE = 200000  # 200KB total context
    
    def __init__(self, work_dir: Path):
        self.work_dir = work_dir
        self.context_cache = {}
        
    def analyze_project(self, task_content: str) -> Dict[str, Any]:
        """Analyze project and gather relevant context based on task"""
        context = {
            'project_type': self._detect_project_type(),
            'is_greenfield': self._is_greenfield_project(),
            'relevant_files': {},
            'project_structure': self._get_project_structure(),
            'suggestions': []
        }
        
        # Gather context based on task type
        if self._is_documentation_task(task_content):
            context['relevant_files'].update(self._gather_documentation_context())
            context['suggestions'].append("Consider existing documentation structure")
            
        elif self._is_code_modification_task(task_content):
            context['relevant_files'].update(self._gather_code_context(task_content))
            context['suggestions'].append("Review existing code patterns and style")
            
        elif self._is_new_feature_task(task_content):
            context['relevant_files'].update(self._gather_architecture_context())
            if context['is_greenfield']:
                context['suggestions'].append("This is a new project - consider establishing patterns")
            else:
                context['suggestions'].append("Follow existing project conventions")
                
        # Always include essential files
        context['relevant_files'].update(self._gather_essential_files())
        
        # Add task-specific recommendations
        context['planning_needed'] = self._assess_planning_needs(task_content, context)
        
        return context
    
    def _detect_project_type(self) -> str:
        """Detect the type of project based on files present"""
        if (self.work_dir / 'package.json').exists():
            return 'nodejs'
        elif (self.work_dir / 'requirements.txt').exists() or (self.work_dir / 'setup.py').exists():
            return 'python'
        elif (self.work_dir / 'Cargo.toml').exists():
            return 'rust'
        elif (self.work_dir / 'go.mod').exists():
            return 'go'
        elif (self.work_dir / 'pom.xml').exists():
            return 'java'
        elif any((self.work_dir / f).exists() for f in ['index.html', 'index.htm']):
            return 'web'
        else:
            return 'unknown'
    
    def _is_greenfield_project(self) -> bool:
        """Check if this is a new/empty project"""
        # Count non-hidden files
        file_count = sum(1 for f in self.work_dir.rglob('*') 
                        if f.is_file() and not f.name.startswith('.'))
        return file_count < 3
    
    def _get_project_structure(self) -> Dict[str, Any]:
        """Get a high-level view of project structure"""
        structure = {
            'directories': [],
            'file_count': 0,
            'main_languages': set(),
            'has_tests': False,
            'has_docs': False
        }
        
        for item in self.work_dir.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                structure['directories'].append(item.name)
                if item.name in ['test', 'tests', 'spec', '__tests__']:
                    structure['has_tests'] = True
                elif item.name in ['docs', 'documentation']:
                    structure['has_docs'] = True
                    
        # Count files and detect languages
        for file_path in self.work_dir.rglob('*'):
            if file_path.is_file() and not file_path.name.startswith('.'):
                structure['file_count'] += 1
                ext = file_path.suffix.lower()
                if ext in ['.py', '.js', '.ts', '.go', '.rs', '.java', '.rb']:
                    structure['main_languages'].add(ext[1:])
                    
        structure['main_languages'] = list(structure['main_languages'])
        return structure
    
    def _gather_essential_files(self) -> Dict[str, str]:
        """Gather essential project files"""
        files = {}
        
        # README files
        for readme in self.IMPORTANT_FILES['readme']:
            path = self.work_dir / readme
            if path.exists():
                content = self._read_file_safely(path)
                if content:
                    files[readme] = content
                break
                
        # Package/dependency files
        for pkg_file in self.IMPORTANT_FILES['package']:
            path = self.work_dir / pkg_file
            if path.exists():
                content = self._read_file_safely(path)
                if content:
                    files[pkg_file] = content
                    
        return files
    
    def _gather_code_context(self, task_content: str) -> Dict[str, str]:
        """Gather relevant code files based on task content"""
        files = {}
        keywords = self._extract_keywords(task_content)
        
        # Search for files containing keywords
        for file_path in self.work_dir.rglob('*.py'):  # Extend to other languages
            if self._file_contains_keywords(file_path, keywords):
                content = self._read_file_safely(file_path)
                if content:
                    rel_path = file_path.relative_to(self.work_dir)
                    files[str(rel_path)] = content
                    
                if len(files) >= 5:  # Limit number of files
                    break
                    
        return files
    
    def _gather_documentation_context(self) -> Dict[str, str]:
        """Gather existing documentation"""
        files = {}
        
        # Look for docs directory
        docs_dir = self.work_dir / 'docs'
        if docs_dir.exists():
            for doc_file in docs_dir.rglob('*.md'):
                content = self._read_file_safely(doc_file)
                if content:
                    rel_path = doc_file.relative_to(self.work_dir)
                    files[str(rel_path)] = content
                    
        return files
    
    def _gather_architecture_context(self) -> Dict[str, str]:
        """Gather files that show project architecture"""
        files = {}
        
        # Main entry points
        for main_file in self.IMPORTANT_FILES['main']:
            path = self.work_dir / main_file
            if path.exists():
                content = self._read_file_safely(path)
                if content:
                    files[main_file] = content
                    
        # Configuration files
        for config_file in self.IMPORTANT_FILES['config']:
            path = self.work_dir / config_file
            if path.exists():
                content = self._read_file_safely(path)
                if content:
                    files[config_file] = content
                    
        return files
    
    def _read_file_safely(self, file_path: Path) -> Optional[str]:
        """Read file with size limits and error handling"""
        try:
            if file_path.stat().st_size > self.MAX_FILE_SIZE:
                # Read first part only
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read(self.MAX_FILE_SIZE)
                    return content + "\n... (truncated)"
            else:
                return file_path.read_text(encoding='utf-8')
        except Exception as e:
            logger.warning(f"Could not read {file_path}: {e}")
            return None
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract relevant keywords from task description"""
        # Simple keyword extraction - could be enhanced with NLP
        words = text.lower().split()
        # Filter common words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 
                     'to', 'for', 'of', 'with', 'by', 'from', 'as', 'is', 'was',
                     'are', 'were', 'been', 'be', 'have', 'has', 'had', 'do',
                     'does', 'did', 'will', 'would', 'should', 'could', 'may',
                     'might', 'must', 'shall', 'can', 'need', 'create', 'make',
                     'add', 'update', 'modify', 'change', 'fix', 'implement'}
        
        keywords = [w for w in words if len(w) > 3 and w not in stop_words]
        return keywords[:5]  # Limit keywords
    
    def _file_contains_keywords(self, file_path: Path, keywords: List[str]) -> bool:
        """Check if file contains any of the keywords"""
        try:
            content = file_path.read_text(encoding='utf-8').lower()
            return any(keyword in content for keyword in keywords)
        except Exception:
            return False
    
    def _is_documentation_task(self, task_content: str) -> bool:
        """Check if task is documentation-related"""
        doc_keywords = ['readme', 'documentation', 'docs', 'document', 'explain',
                       'describe', 'guide', 'tutorial', 'instructions']
        return any(kw in task_content.lower() for kw in doc_keywords)
    
    def _is_code_modification_task(self, task_content: str) -> bool:
        """Check if task involves modifying existing code"""
        mod_keywords = ['update', 'modify', 'change', 'fix', 'refactor', 'improve',
                       'optimize', 'enhance', 'debug', 'patch']
        return any(kw in task_content.lower() for kw in mod_keywords)
    
    def _is_new_feature_task(self, task_content: str) -> bool:
        """Check if task involves creating new features"""
        new_keywords = ['create', 'add', 'implement', 'build', 'develop', 'new',
                       'feature', 'functionality', 'capability']
        return any(kw in task_content.lower() for kw in new_keywords)
    
    def _assess_planning_needs(self, task_content: str, context: Dict[str, Any]) -> str:
        """Assess how much planning is needed"""
        # Complex indicators
        complex_keywords = ['system', 'architecture', 'design', 'integrate', 
                          'database', 'api', 'service', 'microservice', 'scale']
        
        is_complex = any(kw in task_content.lower() for kw in complex_keywords)
        is_large_project = context['project_structure']['file_count'] > 50
        is_brownfield = not context['is_greenfield']
        
        if is_complex and is_brownfield and is_large_project:
            return "extensive"  # Needs careful planning and analysis
        elif is_complex or (is_brownfield and is_large_project):
            return "moderate"   # Needs some planning
        elif context['is_greenfield']:
            return "foundational"  # Needs to establish patterns
        else:
            return "minimal"    # Can proceed with simple implementation
    
    def build_context_prompt(self, task: Dict[str, Any], context_info: Dict[str, Any]) -> str:
        """Build an enhanced prompt with context information"""
        prompt_parts = []
        
        # Project overview
        prompt_parts.append(f"""Project Overview:
- Type: {context_info['project_type']}
- Status: {'New Project (Greenfield)' if context_info['is_greenfield'] else 'Existing Project (Brownfield)'}
- Structure: {context_info['project_structure']['file_count']} files in {len(context_info['project_structure']['directories'])} directories
- Languages: {', '.join(context_info['project_structure']['main_languages']) or 'Not detected'}
- Has Tests: {context_info['project_structure']['has_tests']}
- Has Docs: {context_info['project_structure']['has_docs']}""")
        
        # Planning recommendation
        planning_msgs = {
            'extensive': "This is a complex task in an established project. Please analyze thoroughly before implementing.",
            'moderate': "This task requires some planning. Please consider the existing architecture.",
            'foundational': "This is a new project. Please establish good patterns and structure.",
            'minimal': "This is a straightforward task. You can proceed with implementation."
        }
        prompt_parts.append(f"\nPlanning Recommendation: {planning_msgs[context_info['planning_needed']]}")
        
        # Include relevant files
        if context_info['relevant_files']:
            prompt_parts.append("\n--- Relevant Project Files ---")
            for filename, content in context_info['relevant_files'].items():
                # Limit content length
                if len(content) > 5000:
                    content = content[:5000] + "\n... (truncated)"
                prompt_parts.append(f"\n=== {filename} ===\n{content}")
        
        # Suggestions
        if context_info['suggestions']:
            prompt_parts.append("\nSuggestions:")
            for suggestion in context_info['suggestions']:
                prompt_parts.append(f"- {suggestion}")
        
        return '\n'.join(prompt_parts)


class EnhancedTaskExecutor:
    """Enhanced executor with intelligent context awareness"""
    
    def __init__(self, existing_executor):
        # Inherit from existing executor
        self.base_executor = existing_executor
        
    def execute_with_context(self, task: Dict[str, Any], base_context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute task with enhanced context awareness"""
        work_dir = Path(base_context['working_directory'])
        
        # Analyze project context
        analyzer = ContextAnalyzer(work_dir)
        project_context = analyzer.analyze_project(task['content'])
        
        # Build enhanced prompt
        context_prompt = analyzer.build_context_prompt(task, project_context)
        
        # Modify the original prompt to include context
        enhanced_task = task.copy()
        enhanced_task['enhanced_prompt'] = f"""{context_prompt}

--- Original Task ---
{task['content']}

Please execute this task considering the project context above. If this is a complex task, start by outlining your approach."""
        
        # Log context gathering
        logger.info(f"Gathered context for {base_context['project']} project:")
        logger.info(f"- Project type: {project_context['project_type']}")
        logger.info(f"- Greenfield: {project_context['is_greenfield']}")
        logger.info(f"- Relevant files: {len(project_context['relevant_files'])}")
        logger.info(f"- Planning needed: {project_context['planning_needed']}")
        
        # Execute with enhanced context
        return self.base_executor.execute_with_claude(enhanced_task, base_context)


# Example usage and integration point
def enhance_executor(base_executor):
    """Enhance an existing executor with context awareness"""
    return EnhancedTaskExecutor(base_executor)