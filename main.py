import asyncio
import logging
import threading
import os
import time
import json
from flask import Flask, render_template, jsonify, request
from bot import DailymotionUploaderBot
from config import logger, CHUNK_SIZE

# Create Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dailymotion_uploader_secret")
bot_instance = None
bot_thread = None

# Bot Statistics
stats = {
    "start_time": time.time(),
    "uploads_completed": 0,
    "uploads_failed": 0,
    "total_bytes_processed": 0,
    "active_uploads": 0
}

# Task tracking
tasks = {}  # Dictionary to track upload tasks

@app.route('/')
def index():
    """Home page route"""
    return render_template('index.html')

@app.route('/health')
@app.route('/_health')  # Alternative endpoint used by some platforms
@app.route('/livez')    # Kubernetes style health check
@app.route('/readyz')   # Kubernetes style readiness check
def health_check():
    """
    Health check endpoint for Koyeb and other deployment platforms
    Implements Kubernetes-style health/readiness checks for better compatibility
    """
    global bot_instance
    
    # Get bot uptime if available
    uptime = time.time() - stats["start_time"] if stats.get("start_time") else 0
    
    # Check if Telegram bot is connected or waiting for rate limit
    bot_status = "waiting" if bot_instance and getattr(bot_instance, '_waiting_for_flood_wait', False) else "running" if bot_instance else "stopped"
    
    # Determine if the service is truly healthy based on bot status
    is_healthy = bot_status != "stopped"
    
    # For Koyeb and Kubernetes-style health checks
    if not is_healthy and request.path in ('/livez', '/readyz'):
        return "Service is starting up", 503
    
    return jsonify({
        'status': 'healthy' if is_healthy else 'degraded',
        'service': 'dailymotion-uploader-bot',
        'version': '1.0.2',
        'timestamp': time.time(),
        'uptime': round(uptime),
        'bot_status': bot_status,
        'memory_usage': {
            'active_uploads': stats.get('active_uploads', 0),
            'completed_uploads': stats.get('uploads_completed', 0)
        }
    }), 200 if is_healthy else 200  # Still return 200 for dashboard display

@app.route('/status')
def status():
    """Bot status API endpoint"""
    global bot_instance
    uptime = time.time() - stats["start_time"] if bot_instance else 0
    
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
    
@app.route('/tasks/<task_id>')
def get_task(task_id):
    """Get specific task status"""
    if task_id in tasks:
        return jsonify(tasks[task_id])
    else:
        return jsonify({
            'error': 'Task not found'
        }), 404

@app.route('/stop', methods=['POST'])
def stop_bot():
    """Stop the bot"""
    global bot_instance, bot_thread
    
    if bot_instance:
        try:
            # Create a new thread to stop the bot
            def stop_bot_async():
                global bot_instance
                current_bot = bot_instance
                bot_instance = None  # Set to None first to prevent multiple stop attempts
                
                try:
                    # Use a new event loop for the stopping process
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(current_bot.stop())
                    loop.close()
                except Exception as e:
                    logger.error(f"Error stopping bot: {str(e)}")
                
            stop_thread = threading.Thread(target=stop_bot_async)
            stop_thread.daemon = True
            stop_thread.start()
            
            return jsonify({
                'status': 'stopping',
                'message': 'Bot is being stopped'
            })
        except Exception as e:
            logger.error(f"Error in stop_bot route: {str(e)}")
            return jsonify({
                'status': 'error',
                'message': f'Error stopping bot: {str(e)}'
            })
    else:
        return jsonify({
            'status': 'not_running',
            'message': 'Bot is not running'
        })

async def start_bot():
    """Start the Telegram bot"""
    try:
        global bot_instance
        logger.info("Starting Dailymotion Uploader Bot")
        
        # Try to import flood wait error class for better error handling
        FloodWaitError = None
        try:
            from telethon.errors.rpcerrorlist import FloodWaitError
        except ImportError:
            pass
            
        # Create a backoff counter for retry attempts
        max_retries = 5
        retry_counter = 0
        retry_delay = 10  # Initial delay of 10 seconds
        
        while retry_counter < max_retries:
            try:
                # Initialize the bot
                bot_instance = DailymotionUploaderBot()
                
                # Attempt to start the bot
                await bot_instance.start()
                logger.info("Bot started successfully")
                return  # Success, exit the function
                
            except Exception as e:
                # Check if it's a flood wait error
                if FloodWaitError and isinstance(e, FloodWaitError):
                    wait_time = e.seconds
                    
                    # Mark the bot as waiting for flood wait to expire
                    if not hasattr(bot_instance, '_waiting_for_flood_wait'):
                        bot_instance._waiting_for_flood_wait = True
                    
                    # Set a timestamp when the waiting will end
                    bot_instance._flood_wait_until = time.time() + wait_time
                    
                    # Format the wait time in a human-readable format
                    wait_minutes = wait_time // 60
                    wait_seconds = wait_time % 60
                    wait_hours = wait_minutes // 60
                    wait_minutes = wait_minutes % 60
                    
                    if wait_hours > 0:
                        wait_str = f"{wait_hours}h {wait_minutes}m {wait_seconds}s"
                    elif wait_minutes > 0:
                        wait_str = f"{wait_minutes}m {wait_seconds}s"
                    else:
                        wait_str = f"{wait_seconds}s"
                    
                    logger.warning(f"Telegram API flood wait error. Need to wait for {wait_str}")
                    
                    # For very long waits, set a flag but still keep the bot running in limited mode
                    if wait_time > 3600:  # If wait time is more than 1 hour
                        logger.error(f"Telegram API requires a long wait: {wait_str}. "
                                     f"Bot will run in limited mode and retry automatically after {wait_str}.")
                    
                    # Keep the bot instance available for status checks
                    # Wait for the required time + 5 seconds as buffer in background
                    asyncio.create_task(wait_for_flood_wait(wait_time + 5, retry_counter + 1, max_retries))
                    
                    # Return without raising - this will keep the bot instance available
                    # but in a limited state for checking status
                    return
                    
                else:
                    # For other errors, use exponential backoff
                    if retry_counter < max_retries - 1:  # Don't sleep on the last attempt
                        backoff_time = retry_delay * (2 ** retry_counter)
                        logger.warning(f"Error starting bot: {str(e)}. Retrying in {backoff_time} seconds...")
                        await asyncio.sleep(backoff_time)
                        retry_counter += 1
                    else:
                        logger.error(f"Failed to start bot after {max_retries} attempts: {str(e)}")
                        raise
        
        # If we get here, we've exhausted all retries
        raise Exception(f"Failed to start bot after {max_retries} attempts")
            
    except Exception as e:
        logger.error(f"Error in bot function: {str(e)}")
        raise

async def wait_for_flood_wait(wait_time, retry_count, max_retries):
    """Wait for flood wait to expire and then attempt to restart the bot"""
    global bot_instance
    
    try:
        logger.info(f"Waiting for {wait_time} seconds due to Telegram API flood wait...")
        await asyncio.sleep(wait_time)
        
        logger.info("Flood wait time expired, attempting to restart bot...")
        
        # If for some reason bot_instance was cleared, create a new one
        if not bot_instance:
            bot_instance = DailymotionUploaderBot()
        
        # Reset the flag
        bot_instance._waiting_for_flood_wait = False
        if hasattr(bot_instance, '_flood_wait_until'):
            delattr(bot_instance, '_flood_wait_until')
        
        # Try to start the bot again
        try:
            await bot_instance.start()
            logger.info("Bot successfully restarted after flood wait")
        except Exception as e:
            logger.error(f"Failed to restart bot after flood wait: {str(e)}")
            
            # If we've exceeded our retry limit, give up
            if retry_count >= max_retries:
                logger.error(f"Exceeded maximum retry attempts ({max_retries})")
                return
                
            # Otherwise schedule another retry with backoff
            backoff_time = 30 * (2 ** (retry_count - 1))  # Exponential backoff
            logger.info(f"Scheduling retry in {backoff_time} seconds...")
            asyncio.create_task(wait_for_flood_wait(backoff_time, retry_count + 1, max_retries))
    except Exception as e:
        logger.error(f"Error in wait_for_flood_wait: {str(e)}")

def run_bot():
    """Run the bot in a separate thread"""
    asyncio.run(start_bot())

def start_bot_thread():
    """Start the bot in a background thread and clean up old session files"""
    global bot_thread
    
    # Clean up old session files
    try:
        cleanup_old_sessions()
    except Exception as e:
        logger.error(f"Error cleaning up old sessions: {str(e)}")
    
    # Start the bot thread, but only if not already running
    if bot_thread is None or not bot_thread.is_alive():
        # Check if there's already an active bot thread waiting for flood limit to expire
        global bot_instance
        if bot_instance and getattr(bot_instance, '_waiting_for_flood_wait', False):
            # If we're already in a waiting state, don't start a new thread
            logger.info("Bot is already waiting for Telegram API flood wait restriction to expire")
            return
            
        # Start a new bot thread
        bot_thread = threading.Thread(target=run_bot)
        bot_thread.daemon = True
        bot_thread.start()
        logger.info("Bot thread started")

def cleanup_old_sessions():
    """
    Clean up all session files since we're now using memory-based sessions exclusively.
    We don't need to keep any session files on disk.
    """
    try:
        # Find all session files
        for file in os.listdir():
            # Only process session files
            if file.startswith("dailymotion_uploader_bot") and (
                file.endswith(".session") or file.endswith(".session-journal")
            ):
                try:
                    file_path = os.path.join(os.getcwd(), file)
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        logger.info(f"Cleaned up session file: {file_path}")
                except Exception as e:
                    logger.debug(f"Error removing file {file}: {str(e)}")
                    continue
    except Exception as e:
        logger.error(f"Error in cleanup_old_sessions: {str(e)}")

# Utility functions for status tracking
def format_uptime(seconds):
    """Format uptime in human readable format"""
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    if days > 0:
        return f"{int(days)}d {int(hours)}h {int(minutes)}m"
    elif hours > 0:
        return f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
    elif minutes > 0:
        return f"{int(minutes)}m {int(seconds)}s"
    else:
        return f"{int(seconds)}s"

def update_task_status(task_id, status, progress=None, video_url=None, error=None):
    """Update task status in the tasks dictionary"""
    global tasks
    
    if task_id not in tasks:
        tasks[task_id] = {
            'id': task_id,
            'status': status,
            'created_at': time.time(),
            'updated_at': time.time(),
            'progress': 0
        }
    else:
        tasks[task_id]['status'] = status
        tasks[task_id]['updated_at'] = time.time()
    
    if progress is not None:
        tasks[task_id]['progress'] = progress
    
    if video_url is not None:
        tasks[task_id]['video_url'] = video_url
    
    if error is not None:
        tasks[task_id]['error'] = error
    
    # Update global statistics
    global stats
    if status == 'completed':
        stats['uploads_completed'] += 1
        stats['active_uploads'] = max(0, stats['active_uploads'] - 1)
    elif status == 'failed':
        stats['uploads_failed'] += 1
        stats['active_uploads'] = max(0, stats['active_uploads'] - 1)
    elif status == 'uploading' and 'status' in tasks[task_id] and tasks[task_id]['status'] != 'uploading':
        stats['active_uploads'] += 1

# Main function to run when script is executed directly
if __name__ == "__main__":
    try:
        # Start bot in background thread
        start_bot_thread()
        
        # Get port from environment variable or use default (8080)
        port = int(os.environ.get('PORT', 8080))
        
        # Run Flask app in debug mode when executed directly
        app.run(host='0.0.0.0', port=port, debug=True)
    except KeyboardInterrupt:
        logger.info("Application stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
else:
    # When imported by a WSGI server like gunicorn, only start the bot thread
    start_bot_thread()
