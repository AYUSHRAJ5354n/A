import os
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Telegram API credentials
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Admin settings
ADMIN_IDS = []  # List of admin user IDs who can use the bot
admin_ids_str = os.getenv("ADMIN_IDS", "")
if admin_ids_str:
    try:
        # Parse comma-separated list of admin IDs
        ADMIN_IDS = [int(admin_id.strip()) for admin_id in admin_ids_str.split(",") if admin_id.strip()]
    except Exception as e:
        logger.error(f"Error parsing ADMIN_IDS: {str(e)}")
ADMIN_ONLY_MODE = os.getenv("ADMIN_ONLY_MODE", "false").lower() == "true"  # Whether only admins can use the bot

# Dailymotion API credentials
DAILYMOTION_API_KEY = os.getenv("DAILYMOTION_API_KEY")
DAILYMOTION_API_SECRET = os.getenv("DAILYMOTION_API_SECRET")
DAILYMOTION_USERNAME = os.getenv("DAILYMOTION_USERNAME")
DAILYMOTION_PASSWORD = os.getenv("DAILYMOTION_PASSWORD")

# File upload settings
MAX_FILE_SIZE = 5 * 1024 * 1024 * 1024  # 5GB max file size
CHUNK_SIZE = 16 * 1024 * 1024  # 16MB chunks for upload (optimized for speed)
TELEGRAM_DOWNLOAD_CHUNK_SIZE = 4 * 1024 * 1024  # 4MB chunks for Telegram download (4x faster)
TEMP_DOWNLOAD_DIR = "./temp_downloads"
MAX_CONCURRENT_UPLOADS = 3  # Maximum number of concurrent uploads (increased for parallel processing)
UPLOAD_RETRY_COUNT = 3  # Number of retries for failed uploads
UPLOAD_TIMEOUT = 600  # Timeout for upload operations (in seconds, increased for larger chunks)
DOWNLOAD_TIMEOUT = 600  # Timeout for download operations (in seconds, increased for larger chunks)

# Network optimization
CONNECTION_RETRIES = 8  # Increased number of connection retries
REQUEST_TIMEOUT = 120  # Extended request timeout in seconds for more stability
RATE_LIMIT_DELAY = 3  # Reduced delay between requests when rate limited (in seconds)
TCP_KEEPALIVE = True  # Enable TCP keepalive for maintaining connections
TCP_NODELAY = True  # Disable Nagle's algorithm for faster small packets

# Performance settings
USE_ASYNC_IO = True  # Use async IO for file operations
USE_PARALLEL_TRANSFERS = True  # Enable parallel transfers for better throughput
MAX_CONCURRENT_DOWNLOADS = 2  # Maximum number of parallel downloads
IO_BUFFER_SIZE = 16 * 1024 * 1024  # 16MB IO buffer for faster disk operations
PROGRESS_UPDATE_INTERVAL = 5  # Reduced frequency of progress updates (less overhead)

# Ensure temp directory exists
if not os.path.exists(TEMP_DOWNLOAD_DIR):
    os.makedirs(TEMP_DOWNLOAD_DIR)
