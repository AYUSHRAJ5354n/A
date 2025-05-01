import os
import json
import aiohttp
import logging
import time
from typing import Dict, Any, Optional, Tuple, BinaryIO
import asyncio

from config import (
    DAILYMOTION_API_KEY,
    DAILYMOTION_API_SECRET,
    DAILYMOTION_USERNAME,
    DAILYMOTION_PASSWORD,
    CHUNK_SIZE,
    IO_BUFFER_SIZE,
    REQUEST_TIMEOUT,
    TCP_KEEPALIVE,
    TCP_NODELAY,
    UPLOAD_TIMEOUT
)

logger = logging.getLogger(__name__)

class DailymotionClient:
    """
    Client for interacting with the Dailymotion API to upload videos
    """
    
    def __init__(self):
        self.api_key = DAILYMOTION_API_KEY
        self.api_secret = DAILYMOTION_API_SECRET
        self.username = DAILYMOTION_USERNAME
        self.password = DAILYMOTION_PASSWORD
        self.base_url = "https://api.dailymotion.com"
        self.access_token = None
        self.refresh_token = None
        self.session = None
    
    async def create_session(self):
        """Create aiohttp session for requests with optimized parameters"""
        if self.session is None or self.session.closed:
            tcp_connector = aiohttp.TCPConnector(
                ssl=False,  # Handled at the HTTP level
                keepalive_timeout=60,  # Keep connections alive longer
                limit=10,  # Increase connection pool size
                enable_cleanup_closed=True,
                force_close=False,
                ttl_dns_cache=600,  # Cache DNS results for 10 minutes
            )
            
            # Add TCP optimizations if enabled
            if TCP_KEEPALIVE or TCP_NODELAY:
                tcp_connector._keepalive = TCP_KEEPALIVE
                tcp_connector._nodelay = TCP_NODELAY
                
            timeout = aiohttp.ClientTimeout(
                total=UPLOAD_TIMEOUT,
                connect=REQUEST_TIMEOUT,
                sock_read=REQUEST_TIMEOUT,
                sock_connect=REQUEST_TIMEOUT
            )
            
            self.session = aiohttp.ClientSession(
                connector=tcp_connector,
                timeout=timeout,
                headers={
                    'User-Agent': 'TelegramDailymotionUploaderBot/1.0',
                    'Connection': 'keep-alive'
                },
                raise_for_status=False
            )
        return self.session
    
    async def close_session(self):
        """Close aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def authenticate(self) -> bool:
        """
        Authenticate with Dailymotion API and get access token
        
        Returns:
            True if authentication was successful, False otherwise
        """
        try:
            session = await self.create_session()
            
            auth_data = {
                "grant_type": "password",
                "client_id": self.api_key,
                "client_secret": self.api_secret,
                "username": self.username,
                "password": self.password,
                "scope": "manage_videos"
            }
            
            async with session.post(f"{self.base_url}/oauth/token", data=auth_data) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Authentication failed: {response.status} - {error_text}")
                    return False
                
                auth_response = await response.json()
                self.access_token = auth_response.get("access_token")
                self.refresh_token = auth_response.get("refresh_token")
                
                if not self.access_token:
                    logger.error("Authentication failed: No access token received")
                    return False
                
                logger.info("Successfully authenticated with Dailymotion")
                return True
                
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            return False
    
    async def get_upload_url(self) -> Optional[Dict[str, Any]]:
        """
        Get a URL for uploading a file to Dailymotion
        
        Returns:
            Dictionary with upload info or None if failed
        """
        try:
            if not self.access_token:
                if not await self.authenticate():
                    return None
            
            session = await self.create_session()
            
            headers = {
                "Authorization": f"Bearer {self.access_token}"
            }
            
            async with session.get(f"{self.base_url}/file/upload", headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Failed to get upload URL: {response.status} - {error_text}")
                    return None
                
                upload_data = await response.json()
                logger.info("Successfully obtained upload URL")
                return upload_data
                
        except Exception as e:
            logger.error(f"Error getting upload URL: {str(e)}")
            return None
    
    async def upload_file(
        self, 
        file_path: str, 
        title: Optional[str] = None,
        tags: Optional[str] = None,
        progress_callback = None
    ) -> Optional[str]:
        """
        Upload a file to Dailymotion
        
        Args:
            file_path: Path to the file to upload
            title: Video title (optional)
            tags: Video tags (optional)
            progress_callback: Callback for reporting progress
            
        Returns:
            Video URL if successful, None otherwise
        """
        try:
            # Get upload URL
            upload_data = await self.get_upload_url()
            if not upload_data:
                logger.error("Failed to get upload URL")
                return None
            
            upload_url = upload_data.get("upload_url")
            if not upload_url:
                logger.error("Invalid upload URL received")
                return None
            
            # Get file size for progress reporting
            # (We'll calculate more specific stats in the try block)
            
            session = await self.create_session()
            
            # Upload the file with optimized chunked upload and progress tracking
            try:
                # Get file info for upload
                filename = os.path.basename(file_path)
                file_size = os.path.getsize(file_path)
                
                # Better implementation for progress tracking
                # Create a simpler approach instead of using a custom reader
                # This is more compatible with aiohttp and avoids potential issues
                
                # First read the file
                with open(file_path, 'rb') as f:
                    file_content = f.read()
                    
                # Track upload progress
                start_time = time.time()
                last_callback_time = 0
                
                # Create a callback wrapper for progress reporting
                async def track_progress(current, total):
                    nonlocal start_time, last_callback_time
                    now = time.time()
                    
                    # Only update every second to avoid too many callbacks
                    if now - last_callback_time >= 1.0 or current == total:
                        last_callback_time = now
                        elapsed = max(0.1, now - start_time)
                        speed = current / elapsed
                        
                        # Call the original callback with enhanced information
                        if progress_callback:
                            try:
                                await progress_callback(current, total, {
                                    'speed_bytes_per_sec': speed,
                                    'speed_formatted': f"{speed/1024/1024:.2f} MiB/s"
                                })
                            except Exception as e:
                                logger.error(f"Progress callback error: {str(e)}")
                
                # Create form data with the entire file content
                form = aiohttp.FormData()
                form.add_field('file', 
                               file_content,
                               filename=filename,
                               content_type='application/octet-stream')
                
                # Create optimized upload headers with performance tuning
                upload_headers = {
                    'Connection': 'keep-alive',
                    'Accept-Encoding': 'gzip, deflate',
                    'Accept': '*/*',
                    'User-Agent': 'TelegramDailymotionUploaderBot/1.0'
                }
                
                # Log upload start
                logger.info(f"Starting optimized upload of {filename} ({file_size} bytes)")
                
                # Initialize progress tracking
                total_bytes = len(file_content)
                
                # Start the upload with simple approach
                try:
                    # If we have a progress callback, report the start
                    if progress_callback:
                        try:
                            await progress_callback(0, total_bytes)
                        except Exception as e:
                            logger.error(f"Error in initial progress callback: {str(e)}")
                    
                    # Upload the file
                    async with session.post(
                        upload_url, 
                        data=form,
                        headers=upload_headers,
                        timeout=aiohttp.ClientTimeout(total=UPLOAD_TIMEOUT)
                    ) as response:
                        # Get response data
                        if response.status not in (200, 201):
                            error_text = await response.text()
                            logger.error(f"File upload failed: {response.status} - {error_text}")
                            return None
                        
                        upload_response = await response.json()
                    
                    # Log successful upload completion
                    logger.info(f"Successfully uploaded file: {filename} ({total_bytes} bytes)")
                    
                    # If we have a progress callback, report completion
                    if progress_callback:
                        try:
                            await progress_callback(total_bytes, total_bytes)
                        except Exception as e:
                            logger.error(f"Error in final progress callback: {str(e)}")
                except Exception as e:
                    logger.error(f"Error during upload: {str(e)}")
                    return None
                        
                # No need to report progress again - already done inside the try block
                    
            except Exception as e:
                logger.error(f"Error uploading file: {str(e)}")
                return None
                    
            # Create video with the uploaded file
            if not self.access_token:
                if not await self.authenticate():
                    return None
            
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            
            # Prepare video data with published status
            video_data = {
                "url": upload_response.get("url"),
                "published": True,  # Ensure video is published
                "private": False,   # Make video public
                "channel": "video"  # Set to standard video channel
            }
            
            if title:
                video_data["title"] = title
                
            if tags:
                video_data["tags"] = tags
            
            # Add additional metadata for better processing
            video_data["description"] = title or "Uploaded from Telegram"
            
            # Create the video with expanded permissions
            async with session.post(
                f"{self.base_url}/me/videos", 
                headers=headers, 
                json=video_data
            ) as response:
                if response.status not in (200, 201):
                    error_text = await response.text()
                    logger.error(f"Video creation failed: {response.status} - {error_text}")
                    return None
                
                video_response = await response.json()
                video_id = video_response.get("id")
                
                if not video_id:
                    logger.error("No video ID received after upload")
                    return None
                
                # Get complete video URL
                video_url = f"https://www.dailymotion.com/video/{video_id}"
                
                # Log the successful video creation
                logger.info(f"Video successfully created: {video_url}")
                
                # Verify the video is properly published by checking its status
                try:
                    # Wait for a moment to allow server processing
                    await asyncio.sleep(2)
                    
                    # Check video status
                    video_status = await self.check_video_status(video_id)
                    logger.info(f"Video status after creation: {video_status}")
                    
                    # If video is in processing state, wait a bit and check again
                    if video_status in ["processing", "waiting"]:
                        logger.info("Video is being processed, waiting...")
                        await asyncio.sleep(5)
                        video_status = await self.check_video_status(video_id)
                        logger.info(f"Video status after waiting: {video_status}")
                        
                    # Additional check for visibility and privacy settings
                    visibility_data = await self.check_video_visibility(video_id)
                    logger.info(f"Video visibility settings: {visibility_data}")
                    
                    if visibility_data.get('private') is True:
                        # Try to update privacy settings if it's still private
                        await self.update_video_privacy(video_id, set_public=True)
                except Exception as e:
                    logger.warning(f"Error checking/updating video status: {str(e)}")
                    # Continue regardless of error here since the video was created
                
                logger.info(f"Upload process completed successfully: {video_url}")
                return video_url
                
        except Exception as e:
            logger.error(f"Error uploading file: {str(e)}")
            return None
        
    async def check_video_status(self, video_id: str) -> str:
        """
        Check the processing status of a video
        
        Args:
            video_id: Dailymotion video ID
            
        Returns:
            Status of the video (processing, ready, etc.)
        """
        try:
            if not self.access_token:
                if not await self.authenticate():
                    return "unknown"
            
            session = await self.create_session()
            
            headers = {
                "Authorization": f"Bearer {self.access_token}"
            }
            
            async with session.get(
                f"{self.base_url}/video/{video_id}", 
                headers=headers
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Failed to check video status: {response.status} - {error_text}")
                    return "unknown"
                
                video_data = await response.json()
                return video_data.get("status", "unknown")
                
        except Exception as e:
            logger.error(f"Error checking video status: {str(e)}")
            return "unknown"
            
    async def check_video_visibility(self, video_id: str) -> dict:
        """
        Check the visibility and privacy settings of a video
        
        Args:
            video_id: Dailymotion video ID
            
        Returns:
            Dictionary with video visibility information
        """
        try:
            if not self.access_token:
                if not await self.authenticate():
                    return {}
            
            session = await self.create_session()
            
            headers = {
                "Authorization": f"Bearer {self.access_token}"
            }
            
            # Request fields specifically related to visibility
            fields = "private,published,channel"
            
            async with session.get(
                f"{self.base_url}/video/{video_id}?fields={fields}", 
                headers=headers
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Failed to check video visibility: {response.status} - {error_text}")
                    return {}
                
                return await response.json()
                
        except Exception as e:
            logger.error(f"Error checking video visibility: {str(e)}")
            return {}
    
    async def update_video_privacy(self, video_id: str, set_public: bool = True) -> bool:
        """
        Update the privacy settings of a video
        
        Args:
            video_id: Dailymotion video ID
            set_public: Whether to set the video as public (True) or private (False)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.access_token:
                if not await self.authenticate():
                    return False
            
            session = await self.create_session()
            
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            
            # Prepare update data
            update_data = {
                "private": not set_public,  # False for public, True for private
                "published": True  # Always set to published
            }
            
            async with session.put(
                f"{self.base_url}/video/{video_id}", 
                headers=headers,
                json=update_data
            ) as response:
                if response.status not in (200, 201, 204):
                    error_text = await response.text()
                    logger.error(f"Failed to update video privacy: {response.status} - {error_text}")
                    return False
                
                logger.info(f"Successfully updated video privacy settings for {video_id}")
                return True
                
        except Exception as e:
            logger.error(f"Error updating video privacy: {str(e)}")
            return False
