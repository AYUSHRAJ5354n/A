FROM python:3.11-slim

WORKDIR /app

# Install dependencies
# Copy both requirements files if they exist, with fallbacks
COPY requirements*.txt ./
# Try to use requirements.txt first, falling back to requirements-deploy.txt if needed
RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; \
    elif [ -f requirements-deploy.txt ]; then pip install --no-cache-dir -r requirements-deploy.txt; \
    else echo "No requirements file found" && exit 1; fi

# Copy project files
COPY . .

# Set environment variables
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Create necessary directories
RUN mkdir -p ./temp_downloads
RUN mkdir -p ./templates
RUN mkdir -p ./static

# Make startup script executable
RUN chmod +x ./koyeb_startup.sh

# Use startup script as entrypoint - this handles environment setup and starts gunicorn
ENTRYPOINT ["./koyeb_startup.sh"]