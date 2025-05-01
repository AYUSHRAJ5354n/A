#!/usr/bin/env python
"""
Deployment configuration check script for Dailymotion Uploader Bot
This script helps verify the configuration for deploying to various platforms
"""

import os
import json
import subprocess
import sys

def main():
    """Run deployment checks"""
    print("=== Dailymotion Uploader Bot Deployment Check ===")
    print("Verifying configuration for various deployment platforms...\n")
    
    # Check port configuration
    check_port_configuration()
    
    # Check required environment variables
    check_environment_variables()
    
    # Check for platform-specific files
    check_platform_files()
    
    # Final summary
    print("\n=== Summary ===")
    print("The Dailymotion Uploader Bot is ready for deployment!")
    print("Remember to set all the required environment variables on your hosting platform.")
    print("For more information, refer to the project documentation.")

def check_port_configuration():
    """Check port configuration in various files"""
    print("Checking port configuration...")
    
    # Check main.py default port
    try:
        with open('main.py', 'r') as f:
            content = f.read()
            if "PORT, 8080" in content or "PORT:-8080" in content or "'PORT', 8080" in content:
                print("✓ main.py is configured to use port 8080 by default")
            else:
                print("✗ main.py might not be using port 8080 as default")
    except Exception as e:
        print(f"Error checking main.py: {str(e)}")
    
    # Check Procfile
    try:
        with open('Procfile', 'r') as f:
            content = f.read()
            if "--bind 0.0.0.0:$PORT" in content:
                print("✓ Procfile correctly uses $PORT environment variable for Heroku")
            else:
                print("✗ Procfile might not be properly configured for Heroku")
    except Exception as e:
        print(f"Error checking Procfile: {str(e)}")
    
    # Check Dockerfile
    try:
        with open('Dockerfile', 'r') as f:
            content = f.read()
            if "PORT=8080" in content:
                print("✓ Dockerfile sets default port to 8080")
            else:
                print("✗ Dockerfile might not have port 8080 as default")
    except Exception as e:
        print(f"Error checking Dockerfile: {str(e)}")
    
    # Check docker-compose.yml
    try:
        with open('docker-compose.yml', 'r') as f:
            content = f.read()
            if "PORT:-8080" in content:
                print("✓ docker-compose.yml uses port 8080 as default")
            else:
                print("✗ docker-compose.yml might not use port 8080 as default")
    except Exception as e:
        print(f"Error checking docker-compose.yml: {str(e)}")

def check_environment_variables():
    """Check for required environment variables"""
    print("\nChecking required environment variables...")
    
    required_vars = [
        'API_ID', 'API_HASH', 'BOT_TOKEN',
        'DAILYMOTION_API_KEY', 'DAILYMOTION_API_SECRET',
        'DAILYMOTION_USERNAME', 'DAILYMOTION_PASSWORD'
    ]
    
    # Check .env file
    try:
        with open('.env', 'r') as f:
            env_content = f.read()
            
            for var in required_vars:
                if f"{var}=" in env_content:
                    print(f"✓ {var} is defined in .env file")
                else:
                    print(f"✗ {var} is missing from .env file")
    except FileNotFoundError:
        print("No .env file found. Make sure to create one or set environment variables on your hosting platform.")
    except Exception as e:
        print(f"Error checking .env file: {str(e)}")
    
    # Check .env.example
    try:
        with open('.env.example', 'r') as f:
            example_content = f.read()
            print("\nVerifying .env.example template...")
            
            for var in required_vars:
                if var in example_content:
                    print(f"✓ {var} is included in .env.example template")
                else:
                    print(f"✗ {var} is missing from .env.example template")
    except FileNotFoundError:
        print("No .env.example file found. Consider creating one as a template.")
    except Exception as e:
        print(f"Error checking .env.example file: {str(e)}")

def check_platform_files():
    """Check for platform-specific deployment files"""
    print("\nChecking platform-specific deployment files...")
    
    # Heroku
    if os.path.exists('Procfile'):
        print("✓ Procfile exists (required for Heroku)")
    else:
        print("✗ Procfile is missing (required for Heroku)")
    
    if os.path.exists('runtime.txt'):
        print("✓ runtime.txt exists (optional for Heroku)")
    else:
        print("✗ runtime.txt is missing (optional for Heroku)")
    
    # Docker
    if os.path.exists('Dockerfile'):
        print("✓ Dockerfile exists (required for Docker deployments)")
    else:
        print("✗ Dockerfile is missing (required for Docker deployments)")
    
    if os.path.exists('docker-compose.yml'):
        print("✓ docker-compose.yml exists (helpful for Docker deployments)")
    else:
        print("✗ docker-compose.yml is missing (helpful for Docker deployments)")
    
    # Check for health check endpoint (for Koyeb)
    try:
        with open('main.py', 'r') as f:
            content = f.read()
            if "@app.route('/health')" in content:
                print("✓ Health check endpoint exists (required for Koyeb)")
            else:
                print("✗ Health check endpoint might be missing (required for Koyeb)")
    except Exception as e:
        print(f"Error checking health endpoint: {str(e)}")

if __name__ == "__main__":
    main()