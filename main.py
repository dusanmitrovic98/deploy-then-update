import os
from flask import Flask, request, jsonify, send_from_directory, abort, render_template, Response
from dotenv import load_dotenv
import subprocess
import shutil
import git
import threading
import queue
import time
import json
from functools import wraps
from datetime import datetime

load_dotenv()

PORT = int(os.getenv('PORT', 8080))
GITHUB_REPO = os.getenv('GITHUB_REPO')
GITHUB_USER = os.getenv('GITHUB_USER')
GITHUB_EMAIL = os.getenv('GITHUB_EMAIL')
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
SECRET_KEY = os.getenv('SECRET_KEY')
RUNTIME_DIR = 'runtime'
CONFIG_FILE = 'config.json'
PID_FILE = 'runtime.pid'

app = Flask(__name__)

TERMINAL_LOG_FILE = 'terminal.log'
TERMINAL_LOG_MAX_LINES = 1000
ALL_PIDS_FILE = 'runtime.pids'
CONFIG_BACKUP_FILE = 'config.json.bak'

TERMINAL_LOG = []
TERMINAL_QUEUE = queue.Queue()
TERMINAL_LOCK = threading.Lock()

# --- Error handling ---
@app.errorhandler(Exception)
def handle_exception(e):
    return jsonify({'error': str(e)}), 500

# --- Terminal log helpers ---
def append_terminal_log(line):
    with open(TERMINAL_LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line.rstrip() + '\n')
    # Truncate file if too large
    with open(TERMINAL_LOG_FILE, 'r+', encoding='utf-8') as f:
        lines = f.readlines()
        if len(lines) > TERMINAL_LOG_MAX_LINES:
            f.seek(0)
            f.writelines(lines[-TERMINAL_LOG_MAX_LINES:])
            f.truncate()

def get_terminal_log():
    if not os.path.exists(TERMINAL_LOG_FILE):
        return []
    with open(TERMINAL_LOG_FILE, 'r', encoding='utf-8') as f:
        return [line.rstrip() for line in f.readlines()[-TERMINAL_LOG_MAX_LINES:]]

# --- Process management ---
def add_pid(pid):
    pids = get_all_pids()
    pids.add(pid)
    with open(ALL_PIDS_FILE, 'w') as f:
        f.write('\n'.join(str(p) for p in pids))

def remove_pid(pid):
    pids = get_all_pids()
    pids.discard(pid)
    with open(ALL_PIDS_FILE, 'w') as f:
        f.write('\n'.join(str(p) for p in pids))

def get_all_pids():
    if not os.path.exists(ALL_PIDS_FILE):
        return set()
    with open(ALL_PIDS_FILE) as f:
        return set(int(line.strip()) for line in f if line.strip().isdigit())

def kill_all_processes():
    for pid in list(get_all_pids()):
        try:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/F', '/PID', str(pid)], check=True)
            else:
                os.kill(pid, 9)
        except Exception:
            pass
        remove_pid(pid)
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)

# --- Auth with auto-logout on repeated failures ---
FAILED_AUTH = {}
MAX_FAILED = 5
def check_auth():
    auth = request.headers.get('Authorization', '')
    ip = request.remote_addr
    if not auth.startswith('Bearer '):
        FAILED_AUTH[ip] = FAILED_AUTH.get(ip, 0) + 1
        if FAILED_AUTH[ip] > MAX_FAILED:
            time.sleep(2)
        abort(401)
    token = auth.split(' ', 1)[1]
    if token != SECRET_KEY:
        FAILED_AUTH[ip] = FAILED_AUTH.get(ip, 0) + 1
        if FAILED_AUTH[ip] > MAX_FAILED:
            time.sleep(2)
        abort(403)
    FAILED_AUTH[ip] = 0

def run_script(script):
    # If script starts with 'python ' or 'python.exe ', add -u for unbuffered output
    import shlex
    parts = shlex.split(script)
    if parts and parts[0].startswith('python') and '-u' not in parts:
        parts.insert(1, '-u')
        script = ' '.join(shlex.quote(p) for p in parts)
    proc = subprocess.Popen(script, shell=True, cwd=RUNTIME_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    add_pid(proc.pid)
    def log_output():
        for line in proc.stdout:
            append_terminal_log(line)
        proc.wait()
        append_terminal_log(f'[exit code: {proc.returncode}]')
        remove_pid(proc.pid)
    threading.Thread(target=log_output, daemon=True).start()
    with open(PID_FILE, 'w') as f:
        f.write(str(proc.pid))
    return proc

def stop_running_process():
    kill_all_processes()

def load_config():
    import json
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}

def on_rm_error(func, path, exc_info):
    import stat
    # Try to remove read-only attribute and retry
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass

def log_action(msg):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    append_terminal_log(f'[{timestamp}] {msg}')

@app.route('/run', methods=['POST'])
def run_service():
    check_auth()
    config = load_config()
    start_cmd = config.get('start', 'python app.py')
    log_action('Quick Action: Start Services')
    log_action(f'Running: {start_cmd}')
    proc = run_script(start_cmd)
    log_action(f'Service started with PID {proc.pid}')
    return jsonify({'status': 'started', 'pid': proc.pid})

@app.route('/stop', methods=['POST'])
def stop_service():
    check_auth()
    log_action('Quick Action: Stop Services')
    stop_running_process()
    log_action('All services stopped')
    return jsonify({'status': 'stopped'})

@app.route('/restart', methods=['POST'])
def restart_service():
    check_auth()
    log_action('Quick Action: Restart System')
    stop_running_process()
    log_action('All services stopped (for restart)')
    config = load_config()
    start_cmd = config.get('start', 'python app.py')
    log_action(f'Running: {start_cmd}')
    proc = run_script(start_cmd)
    log_action(f'Service restarted with PID {proc.pid}')
    return jsonify({'status': 'restarted', 'pid': proc.pid})

@app.route('/update', methods=['POST'])
def update_service():
    check_auth()
    log_action('Quick Action: Update System')
    stop_running_process()
    log_action('All services stopped (for update)')
    if os.path.exists(RUNTIME_DIR):
        shutil.rmtree(RUNTIME_DIR, onerror=on_rm_error)
        log_action('Runtime directory removed')
    log_action('Cloning latest code from repository')
    git.Repo.clone_from(GITHUB_REPO.replace('https://', f'https://{GITHUB_TOKEN}@'), RUNTIME_DIR)
    log_action('Repository cloned')
    config = load_config()
    build_cmd = config.get('build')
    if build_cmd:
        log_action(f'Running build: {build_cmd}')
        run_script(build_cmd)
    log_action('System update complete')
    return jsonify({'status': 'updated'})

@app.route('/terminal/logs', methods=['GET'])
def get_terminal_logs():
    check_auth()
    # Always read from the persistent log file
    return jsonify({'logs': get_terminal_log()})

@app.route('/terminal/exec', methods=['POST'])
def exec_terminal():
    check_auth()
    data = request.get_json(force=True)
    cmd = data.get('cmd')
    if not cmd:
        return jsonify({'error': 'No command provided'}), 400
    if cmd in ('cls', 'clear'):
        # Clear the persistent log file
        with open(TERMINAL_LOG_FILE, 'w', encoding='utf-8') as f:
            f.write('')
        return jsonify({'status': 'log cleared'})
    append_terminal_log(f'> {cmd}')
    # On Windows, run in cmd.exe for true cmd behavior
    if os.name == 'nt':
        proc = subprocess.Popen(['cmd.exe', '/c', cmd], cwd=RUNTIME_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    else:
        proc = subprocess.Popen(cmd, shell=True, cwd=RUNTIME_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout:
        append_terminal_log(line)
    proc.wait()
    append_terminal_log(f'[exit code: {proc.returncode}]')
    return jsonify({'status': 'done'})

@app.route('/config', methods=['GET', 'PUT'])
def config_json():
    check_auth()
    if request.method == 'GET':
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE) as f:
                return jsonify(json.load(f))
        return jsonify({}), 404
    elif request.method == 'PUT':
        # Validate JSON
        try:
            new_config = json.loads(request.data.decode('utf-8'))
        except Exception as e:
            return jsonify({'error': 'Invalid JSON', 'details': str(e)}), 400
        # Backup
        if os.path.exists(CONFIG_FILE):
            shutil.copy(CONFIG_FILE, CONFIG_BACKUP_FILE)
        with open(CONFIG_FILE, 'w') as f:
            json.dump(new_config, f, indent=2)
        return jsonify({'status': 'saved'})

@app.route('/config/restore', methods=['POST'])
def restore_config():
    check_auth()
    if os.path.exists(CONFIG_BACKUP_FILE):
        shutil.copy(CONFIG_BACKUP_FILE, CONFIG_FILE)
        return jsonify({'status': 'restored'})
    return jsonify({'error': 'No backup found'}), 404

@app.route('/script/<name>', methods=['POST'])
def run_custom_script(name):
    check_auth()
    config = load_config()
    scripts = config.get('scripts', {})
    script_cmd = scripts.get(name)
    if not script_cmd:
        return jsonify({'error': 'Script not found'}), 404
    log_action(f'Script: {name} - {script_cmd}')
    log_action(f'Running script: {name}')
    run_script(script_cmd)
    log_action(f'Script {name} started')
    return jsonify({'status': 'started'})

@app.route('/files', methods=['GET'])
def list_files():
    check_auth()
    files = []
    for root, dirs, filenames in os.walk(RUNTIME_DIR):
        for fname in filenames:
            path = os.path.join(root, fname)
            rel = os.path.relpath(path, RUNTIME_DIR)
            stat = os.stat(path)
            files.append({'name': rel, 'size': stat.st_size, 'mtime': stat.st_mtime})
    return jsonify({'files': files})

@app.route('/files/<path:filename>', methods=['GET', 'PUT', 'POST', 'DELETE'])
def manage_files(filename):
    check_auth()
    # Prevent access to .git* files
    # if filename.startswith('.git'):
    #     abort(404)
    file_path = os.path.join(RUNTIME_DIR, filename)
    if request.method == 'GET':
        if os.path.exists(file_path):
            return send_from_directory(RUNTIME_DIR, filename, as_attachment=True)
        abort(404)
    elif request.method == 'PUT' or request.method == 'POST':
        with open(file_path, 'wb') as f:
            f.write(request.data)
        return jsonify({'status': 'saved'})
    elif request.method == 'DELETE':
        if os.path.exists(file_path):
            os.remove(file_path)
            return jsonify({'status': 'deleted'})
        abort(404)

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT, debug=True)
