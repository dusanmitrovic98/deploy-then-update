import os
import subprocess
import threading
import time
import logging
from flask import current_app

logger = logging.getLogger(__name__)

def setup_update_handler(app):
    @app.before_first_request
    def initialize_repo():
        repo_path = os.path.abspath(os.path.dirname(__file__))
        if not os.path.exists(os.path.join(repo_path, '.git')):
            logger.info("Cloning repository...")
            subprocess.run(['git', 'clone', '--branch', app.config['BRANCH'], 
                            app.config['REPO_URL'], '.'], cwd=repo_path, check=True)
        else:
            logger.info("Repository already exists")

def get_current_commit():
    try:
        result = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], 
                                capture_output=True, text=True, cwd=os.path.dirname(__file__))
        return result.stdout.strip()
    except Exception as e:
        logger.error(f"Error getting commit: {e}")
        return "unknown"

def safe_update():
    """Update the repository without interrupting service"""
    try:
        repo_path = os.path.dirname(__file__)
        
        # Fetch updates
        subprocess.run(['git', 'fetch', 'origin'], cwd=repo_path, check=True)
        
        # Check if update is needed
        current_branch = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            capture_output=True, text=True, cwd=repo_path
        ).stdout.strip()
        
        local_commit = subprocess.run(
            ['git', 'rev-parse', current_branch],
            capture_output=True, text=True, cwd=repo_path
        ).stdout.strip()
        
        remote_commit = subprocess.run(
            ['git', 'rev-parse', f'origin/{current_branch}'],
            capture_output=True, text=True, cwd=repo_path
        ).stdout.strip()
        
        if local_commit == remote_commit:
            return "already-updated", 200
        
        # Reset to latest commit
        subprocess.run(['git', 'reset', '--hard', f'origin/{current_branch}'], 
                       cwd=repo_path, check=True)
        
        # Install new dependencies
        subprocess.run(['pip', 'install', '-r', 'requirements.txt'], 
                       cwd=repo_path, check=True)
        
        return "update-success", 200
        
    except Exception as e:
        logger.error(f"Update failed: {e}")
        return "update-failed", 500