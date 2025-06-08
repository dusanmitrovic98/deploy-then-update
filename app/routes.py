from flask import render_template_string, request, jsonify
from . import app
from .update_handler import get_current_commit, safe_update
import time

@app.route('/')
def home():
    return render_template_string("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Self-Updating Service</title>
            <style>
                body { font-family: Arial, sans-serif; max-width: 800px; margin: 40px auto; }
                .status { padding: 10px; margin: 10px 0; border-radius: 4px; }
                .success { background: #d4edda; color: #155724; }
                .error { background: #f8d7da; color: #721c24; }
                .info { background: #cce5ff; color: #004085; }
            </style>
        </head>
        <body>
            <h1>Self-Updating Web Service</h1>
            <div class="status info">
                Running on port: {{ port }} | Commit: {{ commit }}
            </div>
            <p>Server time: {{ time }}</p>
            
            <h2>Manual Update</h2>
            <form action="/update" method="post">
                <input type="password" name="token" placeholder="Update token" required>
                <button type="submit">Check for Updates</button>
            </form>
            
            <h2>How Updates Work</h2>
            <p>This service will automatically update when you push to GitHub. 
            You can also manually trigger an update using the form above.</p>
        </body>
        </html>
    """, port=app.config['PORT'], commit=get_current_commit(), time=time.ctime())

@app.route('/update', methods=['POST'])
def update():
    # Verify update token
    if request.form.get('token') != app.config['UPDATE_TOKEN']:
        return jsonify({"status": "error", "message": "Invalid token"}), 403
    
    result, status_code = safe_update()
    
    if status_code == 200:
        return jsonify({
            "status": "success", 
            "message": "Update completed successfully. Changes will take effect on next deployment.",
            "commit": get_current_commit()
        })
    else:
        return jsonify({
            "status": "error", 
            "message": "Update failed. Check server logs for details."
        }), 500