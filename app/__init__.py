from flask import Flask
import os
from .update_handler import setup_update_handler

app = Flask(__name__)

# Configuration
app.config['PORT'] = int(os.environ.get('PORT', 5002))
app.config['REPO_URL'] = os.environ.get('REPO_URL', 'https://github.com/yourusername/yourrepo.git')
app.config['UPDATE_TOKEN'] = os.environ.get('UPDATE_TOKEN', '')
app.config['BRANCH'] = os.environ.get('BRANCH', 'main')

# Initialize update handler
setup_update_handler(app)

# Import routes after app is created
from . import routes