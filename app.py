import os
import subprocess
import shutil
import threading
import logging
import signal
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

app = Flask(__name__)

# Load environment variables from .env file
load_dotenv()

# Configuration
REPO_URL = os.environ.get('REPO_URL', 'https://github.com/your/repo.git')
REPO_NAME = os.environ.get('REPO_NAME', 'deployed_repo')
REPO_PATH = os.path.join(os.getcwd(), REPO_NAME)
DEFAULT_RUN_COMMAND = os.environ.get('RUN_COMMAND', 'pip install -r requirements.txt && python app.py')
LOG_FILE = os.path.join(os.getcwd(), 'output.log')
RUN_COMMAND_FILE = os.path.join(os.getcwd(), '.run_command')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('manager.log')
    ]
)
logger = logging.getLogger(__name__)

# State tracking
process = None
is_running = False
operation_lock = threading.Lock()

# Load or initialize run command
def load_run_command():
    """Load run command from file or use default"""
    if os.path.exists(RUN_COMMAND_FILE):
        try:
            with open(RUN_COMMAND_FILE, 'r') as f:
                return f.read().strip()
        except Exception as e:
            logger.error(f"Error loading run command: {str(e)}")
    return DEFAULT_RUN_COMMAND

def save_run_command(command):
    """Save run command to file"""
    try:
        with open(RUN_COMMAND_FILE, 'w') as f:
            f.write(command.strip())
        return True
    except Exception as e:
        logger.error(f"Error saving run command: {str(e)}")
        return False

# Initialize run command
run_command = load_run_command()

def clone_repo():
    """Clone repository from the specified URL"""
    try:
        logger.info(f"Cloning repository from {REPO_URL}")
        result = subprocess.run(
            ['git', 'clone', REPO_URL, REPO_NAME], 
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if result.returncode != 0:
            logger.error(f"Clone failed: {result.stderr}")
            return False, result.stderr
        logger.info("Repository cloned successfully")
        return True, result.stdout
    except Exception as e:
        logger.error(f"Clone exception: {str(e)}")
        return False, str(e)

def run_process(custom_command=None):
    """Run the process in the repository using shell execution"""
    global process, is_running, run_command
    
    if is_running:
        return False, "Process is already running"
    
    try:
        # Ensure the repository exists
        if not os.path.exists(REPO_PATH):
            success, message = clone_repo()
            if not success:
                return False, message
        
        # Use custom command if provided
        if custom_command and custom_command.strip():
            run_command = custom_command.strip()
            save_run_command(run_command)
        
        logger.info(f"Starting process with command: {run_command}")
        
        # Use shell for complex commands
        with open(LOG_FILE, 'w') as log_file:
            process = subprocess.Popen(
                run_command,
                shell=True,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                cwd=REPO_PATH,
                start_new_session=True  # For proper process group management
            )
        is_running = True
        logger.info(f"Process started successfully with PID: {process.pid}")
        return True, "Process started"
    except Exception as e:
        logger.error(f"Error starting process: {str(e)}")
        return False, str(e)

def stop_process():
    """Stop the running process and its children"""
    global process, is_running
    
    if not is_running:
        return False, "No process running"
    
    try:
        logger.info(f"Stopping process with PID: {process.pid}")
        
        # Send SIGTERM to the entire process group
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass  # Process already terminated
        
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            logger.warning("Process didn't terminate gracefully, forcing kill")
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        
        is_running = False
        logger.info("Process stopped successfully")
        return True, "Process stopped"
    except Exception as e:
        logger.error(f"Error stopping process: {str(e)}")
        return False, str(e)

def restart_process():
    """Restart the running process"""
    logger.info("Restarting process")
    success, message = stop_process()
    if success:
        return run_process()
    return False, message

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
            return True, "Repository removed"
        return False, "Repository does not exist"
    except Exception as e:
        logger.error(f"Error removing repository: {str(e)}")
        return False, str(e)

def update_repo():
    """Update repository by removing and re-cloning"""
    try:
        logger.info("Starting repository update")
        was_running = is_running
        stop_message = ""
        
        # Stop if running
        if was_running:
            success, stop_message = stop_process()
            if not success:
                return False, f"Failed to stop process: {stop_message}"
            
        # Remove existing repository
        if os.path.exists(REPO_PATH):
            logger.info(f"Removing existing repository: {REPO_PATH}")
            shutil.rmtree(REPO_PATH)
        
        # Re-clone repository
        logger.info(f"Re-cloning repository from {REPO_URL}")
        clone_success, clone_message = clone_repo()
        
        messages = [f"Update: {clone_message}"]
        
        # Restart if it was running
        if was_running and clone_success:
            logger.info("Restarting process after update")
            run_success, run_message = run_process()
            messages.append(f"Restart: {run_message}")
            return run_success, "\n".join(messages)
        
        return clone_success, "\n".join(messages)
    except Exception as e:
        logger.error(f"Update failed: {str(e)}")
        return False, str(e)

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
                success, message = run_process(custom_command)
                response.update(success=success, message=message)
                    
            elif action == 'stop':
                success, message = stop_process()
                response.update(success=success, message=message)
                    
            elif action == 'restart':
                success, message = restart_process()
                response.update(success=success, message=message)
                    
            elif action == 'remove':
                success, message = remove_repo()
                response.update(success=success, message=message)
                    
            elif action == 'update':
                success, message = update_repo()
                response.update(success=success, message=message)
                    
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