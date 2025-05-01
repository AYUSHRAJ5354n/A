#!/bin/bash
# Koyeb startup script for Dailymotion Uploader Bot
# This script is used to ensure proper setup before starting the bot on Koyeb

set -e  # Exit immediately if a command exits with a non-zero status

# Create necessary directories if they don't exist
mkdir -p ./temp_downloads
mkdir -p ./templates
mkdir -p ./static

# Check if requirements.txt exists
if [ ! -f requirements.txt ] && [ -f requirements-deploy.txt ]; then
    echo "Using requirements-deploy.txt as requirements.txt"
    cp requirements-deploy.txt requirements.txt
fi

# Install dependencies if needed
if [ -f requirements.txt ]; then
    echo "Installing dependencies from requirements.txt"
    pip install --no-cache-dir -r requirements.txt
fi

# Check if .env exists, if not create from environment variables
if [ ! -f .env ]; then
    echo "Creating .env file from environment variables"
    
    echo "# Telegram API credentials" > .env
    echo "API_ID=${API_ID}" >> .env
    echo "API_HASH=${API_HASH}" >> .env
    echo "BOT_TOKEN=${BOT_TOKEN}" >> .env
    
    echo "" >> .env
    echo "# Dailymotion API credentials" >> .env
    echo "DAILYMOTION_API_KEY=${DAILYMOTION_API_KEY}" >> .env
    echo "DAILYMOTION_API_SECRET=${DAILYMOTION_API_SECRET}" >> .env
    echo "DAILYMOTION_USERNAME=${DAILYMOTION_USERNAME}" >> .env
    echo "DAILYMOTION_PASSWORD=${DAILYMOTION_PASSWORD}" >> .env
    
    echo "" >> .env
    echo "# Admin settings" >> .env
    echo "ADMIN_IDS=${ADMIN_IDS}" >> .env
    echo "ADMIN_ONLY_MODE=${ADMIN_ONLY_MODE:-true}" >> .env
    
    echo "" >> .env
    echo "# Server settings" >> .env
    echo "PORT=${PORT:-8080}" >> .env
fi

# Make main.py executable
chmod +x main.py

# Check for templates directory and index.html
if [ ! -f ./templates/index.html ]; then
    echo "Warning: templates/index.html is missing. Web interface may not work correctly."
fi

# Run gunicorn with optimized settings for Koyeb
exec gunicorn main:app --bind 0.0.0.0:${PORT:-8080} --workers 4 --threads 8 --timeout 120 --keep-alive 5 --max-requests 1000 --max-requests-jitter 50