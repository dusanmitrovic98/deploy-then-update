import os
import subprocess
import shutil
import threading
import logging
import signal
import json
from flask import Flask, render_template, request, jsonify, Response
from dotenv import load_dotenv
import requests
from werkzeug.serving import make_server
import time

app = Flask(__name__)

# Load environment variables
load_dotenv()

# Configuration
REPO_URL = os.environ.get('REPO_URL', 'https://github.com/your/repo.git')
REPO_NAME = os.environ.get('REPO_NAME', 'deployed_repo')
REPO_PATH = os.path.join(os.getcwd(), REPO_NAME)
DEFAULT_CONFIG = {
    'build_command': 'pip install -r requirements.txt',
    'run_command': 'python app.py',
    'ports': [],
    'venv': False
}
CONFIG_FILE = os.path.join(os.getcwd(), 'repo_config.json')
LOG_FILE = os.path.join(os.getcwd(), 'output.log')
VENV_PATH = os.path.join(REPO_PATH, 'venv')

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
active_ports = {}
config = DEFAULT_CONFIG

# Load or initialize configuration
def load_config():
    global config
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                logger.info("Configuration loaded")
        else:
            save_config()
    except Exception as e:
        logger.error(f"Error loading config: {str(e)}")
        config = DEFAULT_CONFIG

def save_config():
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        logger.info("Configuration saved")
        return True
    except Exception as e:
        logger.error(f"Error saving config: {str(e)}")
        return False

# Initialize
load_config()

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

def create_venv():
    """Create virtual environment"""
    try:
        if not os.path.exists(VENV_PATH):
            logger.info("Creating virtual environment")
            result = subprocess.run(
                ['python', '-m', 'venv', VENV_PATH],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=REPO_PATH
            )
            if result.returncode != 0:
                logger.error(f"VENV creation failed: {result.stderr}")
                return False, result.stderr
            logger.info("Virtual environment created")
            config['venv'] = True
            save_config()
            return True, "Virtual environment created"
        return False, "Virtual environment already exists"
    except Exception as e:
        logger.error(f"VENV exception: {str(e)}")
        return False, str(e)

def remove_venv():
    """Remove virtual environment"""
    try:
        if os.path.exists(VENV_PATH):
            logger.info("Removing virtual environment")
            shutil.rmtree(VENV_PATH)
            config['venv'] = False
            save_config()
            return True, "Virtual environment removed"
        return False, "Virtual environment does not exist"
    except Exception as e:
        logger.error(f"VENV removal error: {str(e)}")
        return False, str(e)

def get_activation_prefix():
    """Get command prefix to activate virtual environment"""
    if config['venv']:
        if os.name == 'nt':  # Windows
            return f"{VENV_PATH}\\Scripts\\activate && "
        else:  # Unix/Linux
            return f"source {VENV_PATH}/bin/activate && "
    return ""

def run_process(custom_build=None, custom_run=None):
    """Run the build and app process"""
    global process, is_running
    
    if is_running:
        return False, "Process is already running"
    
    try:
        # Ensure the repository exists
        if not os.path.exists(REPO_PATH):
            success, message = clone_repo()
            if not success:
                return False, message
        
        # Update commands if provided
        if custom_build:
            config['build_command'] = custom_build
        if custom_run:
            config['run_command'] = custom_run
        save_config()
        
        # Create virtual environment if configured
        if config['venv'] and not os.path.exists(VENV_PATH):
            success, message = create_venv()
            if not success:
                return False, message
        
        activation_prefix = get_activation_prefix()
        full_command = f"{activation_prefix}{config['build_command']} && {config['run_command']}"
        
        logger.info(f"Starting process with command: {full_command}")
        
        # Use shell for complex commands
        with open(LOG_FILE, 'w') as log_file:
            process = subprocess.Popen(
                full_command,
                shell=True,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                cwd=REPO_PATH,
                start_new_session=True
            )
        is_running = True
        logger.info(f"Process started successfully with PID: {process.pid}")
        
        # Start port monitoring
        threading.Thread(target=monitor_ports, daemon=True).start()
        
        return True, "Process started"
    except Exception as e:
        logger.error(f"Error starting process: {str(e)}")
        return False, str(e)

def stop_process():
    """Stop the running process and its children"""
    global process, is_running, active_ports
    
    if not is_running:
        return False, "No process running"
    
    try:
        logger.info(f"Stopping process with PID: {process.pid}")
        
        # Clear active ports
        active_ports = {}
        
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

def monitor_ports():
    """Monitor active ports from the process"""
    global active_ports
    while is_running:
        try:
            # Check for open ports (simplified version)
            # In production, use: lsof -i -P -n | grep LISTEN
            new_ports = {}
            for port in config['ports']:
                try:
                    response = requests.get(f"http://localhost:{port}", timeout=1)
                    if response.status_code < 500:
                        new_ports[port] = f":{port} - Active"
                except:
                    new_ports[port] = f":{port} - Inactive"
            
            active_ports = new_ports
            time.sleep(5)
        except Exception as e:
            logger.error(f"Port monitoring error: {str(e)}")
            time.sleep(10)

@app.route('/')
def index():
    repo_exists = os.path.exists(REPO_PATH)
    return render_template(
        'index.html',
        repo_exists=repo_exists,
        is_running=is_running,
        repo_name=REPO_NAME,
        config=config,
        active_ports=active_ports
    )

@app.route('/action', methods=['POST'])
def handle_action():
    action = request.json.get('action')
    build_command = request.json.get('build_command')
    run_command = request.json.get('run_command')
    ports = request.json.get('ports')
    venv_action = request.json.get('venv_action')
    response = {'success': False, 'message': ''}
    
    with operation_lock:
        try:
            if action == 'run':
                success, message = run_process(build_command, run_command)
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
            
            elif action == 'save_config':
                if build_command:
                    config['build_command'] = build_command
                if run_command:
                    config['run_command'] = run_command
                if ports:
                    config['ports'] = [int(p) for p in ports.split(',') if p.strip()]
                save_config()
                response.update(success=True, message="Configuration saved")
                
            elif venv_action == 'create':
                success, message = create_venv()
                response.update(success=success, message=message)
                
            elif venv_action == 'remove':
                success, message = remove_venv()
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
        'active_ports': active_ports
    })

@app.route('/proxy/<int:port>/', defaults={'path': ''})
@app.route('/proxy/<int:port>/<path:path>')
def proxy(port, path):
    """Proxy requests to local services"""
    if port not in config['ports']:
        return "Port not allowed", 403
        
    try:
        url = f'http://localhost:{port}/{path}'
        resp = requests.request(
            method=request.method,
            url=url,
            headers={key: value for (key, value) in request.headers if key.lower() != 'host'},
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False
        )
        
        # Build response
        response = Response(resp.content, resp.status_code)
        for key, value in resp.headers.items():
            if key.lower() not in ['content-encoding', 'transfer-encoding']:
                response.headers[key] = value
        return response
    except Exception as e:
        return str(e), 500

if __name__ == '__main__':
    # Clone repo on startup if not exists
    if not os.path.exists(REPO_PATH):
        clone_repo()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)