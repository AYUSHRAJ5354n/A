import os
import asyncio
import logging
from typing import Dict, Any, Optional, Tuple, Union
import time
from telethon import TelegramClient, events
from telethon.tl.custom import Button
from telethon.tl.types import DocumentAttributeVideo

from config import API_ID, API_HASH, BOT_TOKEN, TEMP_DOWNLOAD_DIR, ADMIN_IDS, ADMIN_ONLY_MODE
from dailymotion import DailymotionClient
from utils import download_file, cleanup_temp_file, format_size, format_time

logger = logging.getLogger(__name__)

class DailymotionUploaderBot:
    """
    Telegram bot for uploading videos to Dailymotion
    """
    
    def __init__(self):
        """Initialize the bot with necessary clients and setup event handlers"""
        # Use memory session to avoid database locks and permission issues
        from telethon.sessions import MemorySession
        self.client = TelegramClient(MemorySession(), API_ID, API_HASH)
        self.dm_client = DailymotionClient()
        self.active_uploads = {}  # Track active uploads by user_id
        self.cancel_requested = {}  # Track cancel requests by user_id
        self.active_tasks = {}  # Track active task IDs by user_id
        
    async def start(self):
        """Start the bot and set up event handlers"""
        await self.client.start(bot_token=BOT_TOKEN)
        
        # Register event handlers
        self.client.add_event_handler(self.handle_start_command, events.NewMessage(pattern='/start'))
        self.client.add_event_handler(self.handle_help_command, events.NewMessage(pattern='/help'))
        self.client.add_event_handler(self.handle_cancel_command, events.NewMessage(pattern='/cancel'))
        self.client.add_event_handler(self.handle_media, events.NewMessage(func=lambda e: e.media))
        self.client.add_event_handler(self.handle_callback, events.CallbackQuery())
        
        logger.info("Bot started successfully")
        
        # Run the client until disconnected
        await self.client.run_until_disconnected()
        
    async def stop(self):
        """Stop the bot gracefully"""
        logger.info("Stopping bot...")
        
        # Close the client connections
        await self.dm_client.close_session()
        await self.client.disconnect()
        
        logger.info("Bot stopped")
    
    async def handle_start_command(self, event):
        """Handle /start command"""
        user_id = event.sender_id
        is_admin = user_id in ADMIN_IDS
        
        # Check if admin-only mode is enabled and user is not an admin
        if ADMIN_ONLY_MODE and not is_admin:
            await event.respond(
                "👋 Welcome to Dailymotion Uploader Bot!\n\n"
                "⛔️ This bot is currently in admin-only mode. "
                "You don't have permission to upload videos at this time."
            )
            return
        
        # Admin or public mode message
        admin_status = "🔑 You are registered as an admin of this bot." if is_admin else ""
        
        await event.respond(
            f"👋 Welcome to Dailymotion Uploader Bot!\n\n"
            f"I can help you upload videos directly from Telegram to Dailymotion.\n\n"
            f"Simply send me any video, and I'll upload it to Dailymotion. "
            f"I can handle files larger than 20MB thanks to Telegram's MTProto.\n\n"
            f"Use /help to see all available commands.\n\n"
            f"{admin_status}"
        )
    
    async def handle_help_command(self, event):
        """Handle /help command"""
        user_id = event.sender_id
        is_admin = user_id in ADMIN_IDS
        
        # Basic help message for all users
        help_message = (
            "📖 **Dailymotion Uploader Bot Help**\n\n"
            "**Commands:**\n"
            "/start - Start the bot\n"
            "/help - Display this help message\n"
            "/cancel - Cancel active download or upload\n\n"
            
            "**How to upload:**\n"
            "1. Simply send any video file to the bot\n"
            "2. Add an optional caption with the following format to set title and tags:\n"
            "   Title: Your Video Title\n"
            "   Tags: tag1, tag2, tag3\n\n"
            
            "**Features:**\n"
            "- Handles large files (over 20MB)\n"
            "- Shows upload progress\n"
            "- Provides Dailymotion link once upload is complete\n\n"
            
            "**Note:** The maximum file size is determined by Telegram (up to 2GB)"
        )
        
        # Add admin-specific help info for admins
        if is_admin:
            admin_message = (
                "\n\n🔑 **Admin Features:**\n"
                "- You can process multiple uploads simultaneously\n"
                "- You have access even in admin-only mode\n"
                "- Your uploads have priority in queue management\n"
                "- Set bot mode with ADMIN_ONLY_MODE environment variable\n"
                "- Add admin IDs with ADMIN_IDS environment variable"
            )
            help_message += admin_message
        
        # Add access restriction notice if in admin-only mode
        if ADMIN_ONLY_MODE and not is_admin:
            restricted_message = (
                "\n\n⚠️ **Access Restriction:**\n"
                "This bot is currently in admin-only mode. "
                "Only authorized administrators can upload files."
            )
            help_message += restricted_message
            
        await event.respond(help_message)
    
    async def handle_media(self, event):
        """
        Handle media files (videos, documents) sent to the bot
        """
        user_id = event.sender_id
        
        # Check if admin-only mode is enabled and user is not an admin
        if ADMIN_ONLY_MODE and user_id not in ADMIN_IDS:
            await event.respond("⛔️ Sorry, this bot is currently in admin-only mode. You don't have permission to use it.")
            return
            
        # For admins, we don't restrict concurrent uploads
        is_admin = user_id in ADMIN_IDS
        
        # Check if user already has an active upload (skip for admins)
        # Add a timestamp check to automatically clear stale entries older than 30 minutes
        if not is_admin and user_id in self.active_uploads:
            # Check if the timestamp is older than 30 minutes
            upload_timestamp = self.active_uploads.get(user_id, {}).get('timestamp', 0)
            if time.time() - upload_timestamp < 1800:  # 30 minutes in seconds
                await event.respond("⚠️ You already have an active upload. Please wait for it to finish.")
                return
            else:
                # Clear stale upload entry
                logger.info(f"Clearing stale upload entry for user {user_id}")
                del self.active_uploads[user_id]
        
        # Mark this user as having an active upload with current timestamp
        self.active_uploads[user_id] = {
            'timestamp': time.time(),
            'active': True
        }
        
        try:
            # Send initial status message
            status_msg = await event.respond("🔄 Processing your file...")
            
            # Check if the file is a valid video
            if not self.is_valid_media(event.media):
                await status_msg.edit("❌ Invalid file format. Please send a video file.")
                del self.active_uploads[user_id]
                return
            
            # Extract title and tags from caption if available
            title, tags = self.extract_metadata_from_caption(event.raw_text if event.raw_text else "")
            
            # Get default title from filename if not provided
            if not title and hasattr(event.media, 'document') and hasattr(event.media.document, 'attributes'):
                for attr in event.media.document.attributes:
                    if hasattr(attr, 'file_name'):
                        title = os.path.splitext(attr.file_name)[0]
                        break
            
            # Use a generic title if still not available
            if not title:
                title = f"Uploaded video {int(time.time())}"
            
            # Download the file with progress updates
            await status_msg.edit("⬇️ Downloading file from Telegram...")
            
            # Set up a progress callback for download
            start_time = time.time()
            file_size = 0
            task_id = f"download_{user_id}_{int(time.time())}"
            
            # Update the main.py task tracking
            from main import update_task_status
            update_task_status(task_id, "downloading", progress=0)
            
            async def download_progress_callback(current, total, stats=None):
                nonlocal start_time, file_size, task_id
                file_size = total
                
                # Check if cancellation was requested
                if user_id in self.cancel_requested and self.cancel_requested[user_id]:
                    logger.info(f"Cancellation requested for user {user_id} during download")
                    # Update status and task tracking
                    update_task_status(task_id, "canceled", progress=0)
                    # Raise exception to cancel the operation
                    raise asyncio.CancelledError("Download canceled by user")
                
                # Calculate progress percentage
                percent = (current / total) * 100 if total > 0 else 0
                
                # Update task status in main.py
                update_task_status(task_id, "downloading", progress=percent)
                
                # If stats are provided, use them for better reporting
                if stats:
                    # Format the progress message with enhanced stats
                    progress_text = (
                        f"⬇️ Downloading: {percent:.1f}%\n"
                        f"Speed: {stats.get('speed_formatted', 'calculating...')}\n"
                        f"ETA: {stats.get('eta_formatted', 'calculating...')}\n"
                        f"Size: {format_size(current)} / {format_size(total)}"
                    )
                else:
                    # Calculate basic stats if not provided
                    elapsed = time.time() - start_time
                    speed = current / elapsed if elapsed > 0 else 0
                    
                    # Format the progress message
                    progress_text = (
                        f"⬇️ Downloading: {percent:.1f}%\n"
                        f"Speed: {format_size(speed)}/s\n"
                        f"Size: {format_size(current)} / {format_size(total)}"
                    )
                
                # Create cancel button
                buttons = [Button.inline("❌ Cancel Download", data="cancel_download")]
                
                try:
                    # Update status message with progress and cancel button
                    asyncio.create_task(status_msg.edit(progress_text, buttons=buttons))
                except Exception as e:
                    # Ignore errors updating message too frequently
                    logger.debug(f"Error updating status: {str(e)}")
            
            # Download the file
            try:
                file_path, file_name = await download_file(
                    event.message,
                    progress_callback=download_progress_callback
                )
                
                if not file_path or not os.path.exists(file_path):
                    await status_msg.edit("❌ Failed to download file from Telegram.")
                    del self.active_uploads[user_id]
                    return
            except asyncio.CancelledError:
                # Handle user cancellation
                await status_msg.edit("❌ Download cancelled by user.")
                del self.active_uploads[user_id]
                return
            except Exception as e:
                # Handle other errors
                logger.error(f"Download error: {str(e)}")
                await status_msg.edit(f"❌ Download error: {str(e)[:100]}...")
                del self.active_uploads[user_id]
                return
            
            # Update status
            await status_msg.edit(f"✅ Download complete!\n\nPreparing to upload to Dailymotion as:\nTitle: {title}\nTags: {tags if tags else 'None'}")
            
            # Upload to Dailymotion
            await status_msg.edit("⬆️ Uploading to Dailymotion...")
            
            # Create a new task ID for upload tracking
            upload_task_id = f"upload_{user_id}_{int(time.time())}"
            
            # Update task status to uploading
            update_task_status(upload_task_id, "uploading", progress=0)
            
            # Set up progress callback for upload with stats tracking
            start_time = time.time()
            file_stat = os.stat(file_path)
            total_size = file_stat.st_size
            
            async def upload_progress_callback(current, total):
                nonlocal start_time, upload_task_id
                
                # Check if cancellation was requested
                if user_id in self.cancel_requested and self.cancel_requested[user_id]:
                    logger.info(f"Cancellation requested for user {user_id} during upload")
                    # Update status and task tracking
                    update_task_status(upload_task_id, "canceled", progress=0)
                    # Raise exception to cancel the operation
                    raise asyncio.CancelledError("Upload canceled by user")
                
                # Calculate progress percentage
                percent = (current / total) * 100 if total > 0 else 0
                
                # Update task status
                update_task_status(upload_task_id, "uploading", progress=percent)
                
                # Calculate speed and ETA
                elapsed = time.time() - start_time
                speed = current / elapsed if elapsed > 0 else 0
                eta = (total - current) / speed if speed > 0 else 0
                
                # Format progress message
                progress_text = (
                    f"⬆️ Uploading to Dailymotion: {percent:.1f}%\n"
                    f"Speed: {format_size(speed)}/s\n"
                    f"ETA: {format_time(eta)}\n"
                    f"Size: {format_size(current)} / {format_size(total)}"
                )
                
                # Create cancel button
                buttons = [Button.inline("❌ Cancel Upload", data="cancel_upload")]
                
                try:
                    # Update status message with progress and cancel button
                    asyncio.create_task(status_msg.edit(progress_text, buttons=buttons))
                except Exception as e:
                    # Ignore errors updating message too frequently
                    logger.debug(f"Error updating status: {str(e)}")
                
                # Update global statistics in main.py
                from main import stats
                stats['total_bytes_processed'] += current
            
            # Upload the file with progress tracking
            video_url = await self.dm_client.upload_file(
                file_path=file_path,
                title=title,
                tags=tags,
                progress_callback=upload_progress_callback
            )
            
            # Update task status based on result
            if video_url:
                update_task_status(upload_task_id, "completed", video_url=video_url)
                # Update upload stats
                from main import stats
                stats['uploads_completed'] += 1
            else:
                update_task_status(upload_task_id, "failed", error="Failed to upload to Dailymotion")
                # Update failure stats
                from main import stats
                stats['uploads_failed'] += 1
            
            # Clean up the temporary file
            await cleanup_temp_file(file_path)
            
            if video_url:
                # Success message with buttons
                buttons = [
                    [Button.url("Watch on Dailymotion", video_url)]
                ]
                await status_msg.edit(
                    f"✅ Upload successful!\n\n"
                    f"Title: {title}\n"
                    f"Your video is now available on Dailymotion.",
                    buttons=buttons
                )
            else:
                await status_msg.edit("❌ Failed to upload to Dailymotion. Please try again later.")
        
        except Exception as e:
            logger.error(f"Error handling media: {str(e)}")
            await event.respond(f"❌ An error occurred: {str(e)}")
        
        finally:
            # Mark upload as complete
            if user_id in self.active_uploads:
                del self.active_uploads[user_id]
    
    def is_valid_media(self, media):
        """
        Check if the media is a valid file for upload
        
        Args:
            media: Telegram media object
            
        Returns:
            True if media is valid for upload, False otherwise
        """
        if hasattr(media, 'document'):
            mime_type = media.document.mime_type
            # Check if it's a video or a document that might be a video
            if mime_type.startswith('video/') or mime_type == 'application/octet-stream':
                return True
            
        return False
    
    def extract_metadata_from_caption(self, caption_text):
        """
        Extract title and tags from message caption
        
        Args:
            caption_text: Caption text from the message
            
        Returns:
            Tuple of (title, tags)
        """
        title = None
        tags = None
        
        if not caption_text:
            return title, tags
        
        # Split caption into lines
        lines = caption_text.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Extract title
            if line.lower().startswith('title:'):
                title = line[6:].strip()
            
            # Extract tags
            if line.lower().startswith('tags:'):
                tags = line[5:].strip()
        
        return title, tags
        
    async def handle_cancel_command(self, event):
        """Handle /cancel command - cancel active downloads/uploads"""
        user_id = event.sender_id
        
        # Check if admin-only mode is enabled and user is not an admin
        if ADMIN_ONLY_MODE and user_id not in ADMIN_IDS:
            await event.respond("⛔️ Sorry, this bot is currently in admin-only mode. You don't have permission to use it.")
            return
            
        # Check if user is an admin
        is_admin = user_id in ADMIN_IDS
        
        # Check if user has an active upload with timestamp-based stale detection
        if user_id in self.active_uploads:
            # Check if it's a stale entry
            upload_data = self.active_uploads.get(user_id, {})
            upload_timestamp = upload_data.get('timestamp', 0) if isinstance(upload_data, dict) else 0
            
            if time.time() - upload_timestamp > 1800:  # 30 minutes in seconds
                # Clear stale upload entry
                logger.info(f"Clearing stale upload entry for user {user_id}")
                del self.active_uploads[user_id]
                await event.respond("❕ You don't have any active uploads to cancel.")
                return
                
            # Mark as canceled
            self.cancel_requested[user_id] = True
            
            # Send confirmation with admin status if applicable
            admin_status = " with admin priority" if is_admin else ""
            await event.respond(f"🛑 Cancellation requested{admin_status}. The operation will be aborted as soon as possible.")
        else:
            await event.respond("❕ You don't have any active uploads to cancel.")
    
    async def handle_callback(self, event):
        """Handle callback queries from inline buttons"""
        user_id = event.sender_id
        data = event.data.decode('utf-8')
        
        # Check if admin-only mode is enabled and user is not an admin
        if ADMIN_ONLY_MODE and user_id not in ADMIN_IDS:
            await event.answer("⛔️ Sorry, this bot is in admin-only mode. You don't have permission.", alert=True)
            return
            
        # Check if user is an admin
        is_admin = user_id in ADMIN_IDS
        
        if data == 'cancel_upload':
            if user_id not in self.active_uploads:
                await event.answer("No active upload to cancel", alert=True)
                return
            
            # Mark as canceled
            self.cancel_requested[user_id] = True
            
            # Notify user
            admin_text = " with admin priority" if is_admin else ""
            await event.answer(f"Upload will be canceled shortly{admin_text}", alert=True)
            
            # Update the message
            if hasattr(event, 'message') and event.message:
                admin_indicator = "🔑 " if is_admin else ""
                await event.message.edit(f"{admin_indicator}⏹️ Canceling upload...")
        
        elif data == 'cancel_download':
            if user_id not in self.active_uploads:
                await event.answer("No active download to cancel", alert=True)
                return
            
            # Mark as canceled
            self.cancel_requested[user_id] = True
            
            # Notify user
            admin_text = " with admin priority" if is_admin else ""
            await event.answer(f"Download will be canceled shortly{admin_text}", alert=True)
            
            # Update the message
            if hasattr(event, 'message') and event.message:
                admin_indicator = "🔑 " if is_admin else ""
                await event.message.edit(f"{admin_indicator}⏹️ Canceling download...")
