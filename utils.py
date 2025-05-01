import os
import aiohttp
import asyncio
import time
import uuid
from typing import Dict, Any, Optional, Tuple, BinaryIO, Callable
import logging

from config import (
    TEMP_DOWNLOAD_DIR, 
    CHUNK_SIZE, 
    TELEGRAM_DOWNLOAD_CHUNK_SIZE,
    DOWNLOAD_TIMEOUT,
    PROGRESS_UPDATE_INTERVAL,
    IO_BUFFER_SIZE,
    MAX_CONCURRENT_DOWNLOADS,
    USE_PARALLEL_TRANSFERS,
    TCP_KEEPALIVE,
    TCP_NODELAY
)
from telethon.tl.custom import Message

logger = logging.getLogger(__name__)

async def download_file(
    message: Message, 
    progress_callback=None
) -> Tuple[Optional[str], Optional[str]]:
    """
    Download a file from Telegram message with optimized parameters
    
    Args:
        message: Telegram message containing the file
        progress_callback: Optional callback to report download progress
        
    Returns:
        Tuple containing (file_path, file_name) or (None, None) if failed
    """
    try:
        if not hasattr(message, 'media'):
            return None, None
        
        # Track download start time for stats
        start_time = time.time()    
        
        # Generate a unique ID for this download
        task_id = str(uuid.uuid4())
        
        # Get or generate file name
        file_name = message.file.name
        if not file_name:
            # Generate a name if none exists
            if hasattr(message.media, 'document'):
                for attr in message.media.document.attributes:
                    if hasattr(attr, 'file_name'):
                        file_name = attr.file_name
                        break
            
            if not file_name:
                # Use message ID as filename if no name found
                extension = get_extension_from_mime(message)
                file_name = f"file_{message.id}{extension}"
        
        # Create a path in the temp directory
        file_path = os.path.join(TEMP_DOWNLOAD_DIR, file_name)
        
        # Rate limiting for progress callbacks
        last_progress_time = 0
        
        # Wrapper for progress callback to control frequency and add stats
        async def optimized_progress_callback(current, total):
            nonlocal last_progress_time
            current_time = time.time()
            
            # Only call the original callback periodically to avoid flood
            if current_time - last_progress_time >= PROGRESS_UPDATE_INTERVAL or current == total:
                last_progress_time = current_time
                
                # Calculate download speed
                elapsed = max(0.1, current_time - start_time)
                speed = current / elapsed
                
                # Calculate ETA
                if speed > 0:
                    eta = (total - current) / speed
                else:
                    eta = 0
                
                # Add stats to callback data
                stats = {
                    "task_id": task_id,
                    "speed_bytes_per_sec": speed,
                    "speed_formatted": format_size(speed) + "/s",
                    "eta_seconds": eta,
                    "eta_formatted": format_time(eta),
                    "elapsed_seconds": elapsed,
                    "elapsed_formatted": format_time(elapsed)
                }
                
                # Call original callback with enhanced data
                if progress_callback:
                    await progress_callback(current, total, stats)
        
        # Download with optimized parameters
        logger.info(f"Starting download of file: {file_name}")
        
        # Using simpler approach that's guaranteed to work
        # Improved error handling and retry mechanism
        max_retries = 2
        retry_count = 0
        last_error = None
        
        while retry_count < max_retries:
            try:
                # Temporary patch to speed up downloads without risking compatibility issues
                # If client has the property, try to set it, but don't worry if it fails
                if hasattr(message, 'client'):
                    try:
                        # Try to set chunk size for faster downloads
                        client = message.client
                        client._get_proper_filename = lambda *args, **kwargs: file_path
                        if hasattr(client, '_download_part_size'):
                            original_part_size = getattr(client, '_download_part_size', 65536)  # Default is usually 64KB
                            client._download_part_size = TELEGRAM_DOWNLOAD_CHUNK_SIZE
                    except Exception as e:
                        logger.warning(f"Could not set custom chunk size: {str(e)}")
                
                # Download using the standard API
                await message.download_media(
                    file=file_path,
                    progress_callback=optimized_progress_callback
                )
                
                # If we get here, download was successful
                break
                
            except asyncio.CancelledError:
                # Don't retry on explicit cancellation
                logger.warning("Download was cancelled by user")
                raise
                
            except Exception as e:
                last_error = e
                logger.error(f"Download error (attempt {retry_count+1}/{max_retries}): {str(e)}")
                retry_count += 1
                
                # Only retry on authorization errors or network issues
                if "authorization" in str(e).lower() or "network" in str(e).lower():
                    if retry_count < max_retries:
                        logger.info(f"Waiting 2 seconds before retry #{retry_count+1}")
                        await asyncio.sleep(2)  # Wait before retrying
                    else:
                        raise  # Raise after all retries are exhausted
                else:
                    # Don't retry on other types of errors
                    raise
        
        download_time = time.time() - start_time
        size_bytes = os.path.getsize(file_path)
        speed = size_bytes / max(0.1, download_time)
        
        logger.info(f"Downloaded file to {file_path} ({format_size(size_bytes)}) in {format_time(download_time)} at {format_size(speed)}/s")
        return file_path, file_name
    except Exception as e:
        logger.error(f"Error downloading file: {str(e)}")
        return None, None

def get_extension_from_mime(message: Message) -> str:
    """
    Get file extension from MIME type in message
    
    Args:
        message: Telegram message
        
    Returns:
        String with file extension including the dot (e.g., ".mp4")
    """
    if hasattr(message.media, 'document') and hasattr(message.media.document, 'mime_type'):
        mime = message.media.document.mime_type
        if mime == 'video/mp4':
            return '.mp4'
        elif mime == 'video/x-matroska':
            return '.mkv'
        elif mime == 'image/jpeg':
            return '.jpg'
        elif mime == 'image/png':
            return '.png'
        elif mime == 'audio/mpeg':
            return '.mp3'
    
    # Default extension if MIME type is not recognized
    return '.bin'

async def cleanup_temp_file(file_path: str) -> None:
    """
    Remove temporary downloaded file
    
    Args:
        file_path: Path to the file to be removed
    """
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Cleaned up temporary file: {file_path}")
    except Exception as e:
        logger.error(f"Error cleaning up file {file_path}: {str(e)}")

def format_size(size_bytes: float) -> str:
    """
    Format file size in a human-readable format
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Human-readable size string
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"

def format_time(seconds: float) -> str:
    """
    Format time in a human-readable format
    
    Args:
        seconds: Time in seconds
        
    Returns:
        Human-readable time string
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes, seconds = divmod(seconds, 60)
        return f"{int(minutes)}m {int(seconds)}s"
    elif seconds < 86400:
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{int(hours)}h {int(minutes)}m"
    else:
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        return f"{int(days)}d {int(hours)}h"
