import subprocess

def get_git_info():
    try:
        commit_hash = subprocess.check_output(
            ['git', 'rev-parse', '--short', 'HEAD'],
            stderr=subprocess.DEVNULL
        ).decode('utf-8').strip()
        
        commit_time = subprocess.check_output(
            ['git', 'log', '-1', '--format=%cd', '--date=relative'],
            stderr=subprocess.DEVNULL
        ).decode('utf-8').strip()
        
        return f"{commit_hash} ({commit_time})"
    except:
        return "unknown"