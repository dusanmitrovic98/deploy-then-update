from flask import Flask
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['PORT'] = int(os.environ.get('PORT', 5002))
app.config['REPO_URL'] = os.environ.get('REPO_URL')
app.config['BRANCH'] = os.environ.get('BRANCH')
app.config['UPDATE_TOKEN'] = os.environ.get('UPDATE_TOKEN')

# Import routes after app is created to avoid circular imports
from app import routes