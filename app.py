# app.py
import os
import subprocess
import shutil
import threading
import logging
from flask import Flask, render_template, request, jsonify, send_from_directory
from dotenv import load_dotenv

app = Flask(__name__)

# Load environment variables from .env file
load_dotenv()

# Configuration
REPO_URL = os.environ.get('REPO_URL', 'https://github.com/your/repo.git')
REPO_NAME = os.environ.get('REPO_NAME', 'deployed_repo')
REPO_PATH = os.path.join(os.getcwd(), REPO_NAME)
DEFAULT_RUN_COMMAND = 'python app.py'  # Default if not set by user
LOG_FILE = os.path.join(os.getcwd(), 'output.log')

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# State tracking
process = None
is_running = False
operation_lock = threading.Lock()
run_command = DEFAULT_RUN_COMMAND  # Store the current run command

def clone_repo():
    """Clone repository from the specified URL"""
    try:
        logger.info(f"Cloning repository from {REPO_URL}")
        subprocess.run(['git', 'clone', REPO_URL, REPO_NAME], 
                       check=True, 
                       capture_output=True,
                       text=True)
        logger.info("Repository cloned successfully")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Clone failed: {e.stderr}")
        return False

def run_process(custom_command=None):
    """Run the process in the repository"""
    global process, is_running, run_command
    
    if is_running:
        return False
    
    try:
        # Ensure the repository exists
        if not os.path.exists(REPO_PATH):
            if not clone_repo():
                return False
        
        # Use custom command if provided
        if custom_command:
            run_command = custom_command
        logger.info(f"Starting process with command: {run_command}")
        with open(LOG_FILE, 'w') as log_file:
            process = subprocess.Popen(
                run_command.split(),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                cwd=REPO_PATH
            )
        is_running = True
        logger.info("Process started successfully")
        return True
    except Exception as e:
        logger.error(f"Error starting process: {str(e)}")
        return False

def stop_process():
    """Stop the running process"""
    global process, is_running
    
    if not is_running:
        return False
    
    try:
        logger.info("Stopping process")
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            logger.warning("Process didn't terminate gracefully, forcing kill")
            process.kill()
            process.wait()
        is_running = False
        logger.info("Process stopped successfully")
        return True
    except Exception as e:
        logger.error(f"Error stopping process: {str(e)}")
        return False

def restart_process():
    """Restart the running process"""
    logger.info("Restarting process")
    if stop_process():
        return run_process()
    return False

def remove_repo():
    """Remove the repository folder"""
    global is_running
    
    try:
        # Stop if running
        if is_running:
            stop_process()
            
        # Remove repository folder
        if os.path.exists(REPO_PATH):
            logger.info(f"Removing repository folder: {REPO_PATH}")
            shutil.rmtree(REPO_PATH)
            logger.info("Repository removed successfully")
            return True
        return False
    except Exception as e:
        logger.error(f"Error removing repository: {str(e)}")
        return False

def update_repo():
    """Update repository by removing and re-cloning"""
    try:
        logger.info("Starting repository update")
        was_running = is_running
        
        # Stop if running
        if was_running:
            stop_process()
            
        # Remove existing repository
        if os.path.exists(REPO_PATH):
            logger.info(f"Removing existing repository: {REPO_PATH}")
            shutil.rmtree(REPO_PATH)
        
        # Re-clone repository
        logger.info(f"Re-cloning repository from {REPO_URL}")
        clone_result = clone_repo()
        
        # Restart if it was running
        if was_running and clone_result:
            logger.info("Restarting process after update")
            run_result = run_process()
            return clone_result and run_result
        
        return clone_result
    except Exception as e:
        logger.error(f"Update failed: {str(e)}")
        return False

@app.route('/')
def index():
    repo_exists = os.path.exists(REPO_PATH)
    return render_template(
        'index.html',
        repo_exists=repo_exists,
        is_running=is_running,
        repo_name=REPO_NAME,
        run_command=run_command
    )

@app.route('/action', methods=['POST'])
def handle_action():
    action = request.json.get('action')
    custom_command = request.json.get('run_command')
    response = {'success': False, 'message': ''}
    
    with operation_lock:
        try:
            if action == 'run':
                if run_process(custom_command):
                    response.update(success=True, message='Repository started')
                else:
                    response.update(message='Failed to start repository')
                    
            elif action == 'stop':
                if stop_process():
                    response.update(success=True, message='Process stopped')
                else:
                    response.update(message='Process was not running')
                    
            elif action == 'restart':
                if restart_process():
                    response.update(success=True, message='Process restarted')
                else:
                    response.update(message='Restart failed')
                    
            elif action == 'remove':
                if remove_repo():
                    response.update(success=True, message='Repository removed')
                else:
                    response.update(message='Nothing to remove or removal failed')
                    
            elif action == 'update':
                if update_repo():
                    response.update(success=True, message='Repository updated successfully')
                else:
                    response.update(message='Update failed')
                    
        except Exception as e:
            logger.exception(f"Action '{action}' failed")
            response['message'] = f'Error: {str(e)}'

    return jsonify(response)

@app.route('/logs')
def view_logs():
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r') as f:
            logs = f.read()
        return render_template('logs.html', logs=logs)
    return "No logs available", 404

@app.route('/status')
def get_status():
    return jsonify({
        'is_running': is_running,
        'repo_exists': os.path.exists(REPO_PATH),
        'run_command': run_command
    })

if __name__ == '__main__':
    # Clone repo on startup if not exists
    if not os.path.exists(REPO_PATH):
        clone_repo()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)