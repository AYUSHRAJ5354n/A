"""
Web dashboard for the Dailymotion Uploader Bot
This runs on a separate port to avoid conflicts with the main application
"""

import os
import sys
import time
import logging
import threading
from flask import Flask, render_template, jsonify, request

# Import main app components
from main import tasks, stats, start_bot_thread, bot_instance, format_uptime, cleanup_old_sessions

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)

@app.route('/')
def index():
    """Home page route"""
    return render_template('index.html')

@app.route('/status')
def status():
    """Bot status API endpoint"""
    global bot_instance
    uptime = time.time() - stats["start_time"] if stats.get("start_time") else 0
    
    return jsonify({
        'status': 'running' if bot_instance else 'stopped',
        'message': 'Dailymotion Uploader Bot is active' if bot_instance else 'Bot is not running',
        'uptime': round(uptime),
        'uptime_formatted': format_uptime(uptime),
        'stats': stats
    })

@app.route('/tasks')
def get_tasks():
    """Get all upload tasks"""
    return jsonify({
        'tasks': tasks
    })

@app.route('/task/<task_id>')
def get_task(task_id):
    """Get specific task status"""
    if task_id in tasks:
        return jsonify({
            'task': tasks[task_id]
        })
    else:
        return jsonify({
            'error': 'Task not found'
        }), 404

if __name__ == "__main__":
    try:
        # Make sure the bot thread is running
        start_bot_thread()
        
        # Run dashboard on port 8080 to avoid conflicts
        port = int(os.environ.get('DASHBOARD_PORT', 8080))
        
        print(f"Dashboard available at: http://localhost:{port}")
        app.run(host='0.0.0.0', port=port, debug=True)
    except KeyboardInterrupt:
        logger.info("Dashboard stopped by user")
    except Exception as e:
        logger.error(f"Dashboard error: {str(e)}")