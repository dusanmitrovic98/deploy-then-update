from flask import render_template
from app import app
from .utils import get_git_info
import time

@app.route('/')
def home():
    return render_template('index.html',
                        port=app.config['PORT'],
                        git_info=get_git_info(),
                        time=time.ctime())

@app.route('/healthz')
def healthz():
    return "ok", 200