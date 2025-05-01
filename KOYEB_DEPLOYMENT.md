# Dailymotion Uploader Bot - Koyeb Deployment Guide

This guide explains how to deploy the Dailymotion Uploader Bot on Koyeb, a developer-friendly serverless platform.

## Prerequisites

1. A Koyeb account - [Sign up here](https://app.koyeb.com/)
2. Your Telegram API credentials (API_ID, API_HASH, BOT_TOKEN)
3. Your Dailymotion API credentials (API_KEY, API_SECRET, USERNAME, PASSWORD)

## Deployment Steps

### Option 1: Using the Koyeb Web Interface

1. **Log in** to your Koyeb account.

2. **Create a new application** by clicking on "Create App".

3. **Choose deployment method**:
   - Select "Docker" as the deployment method
   - Use GitHub as the source and connect to your repository
   - Set the branch to deploy from (usually `main`)

4. **Configure the service**:
   - Name: `dailymotion-uploader-bot`
   - Type: `Web Service`
   - Instance Type: `nano` or `micro` (depending on your needs)
   - Regions: Choose the region closest to your users

5. **Set environment variables**:
   Create the following environment variables as secrets:
   
   ```
   API_ID=your_telegram_api_id
   API_HASH=your_telegram_api_hash
   BOT_TOKEN=your_telegram_bot_token
   DAILYMOTION_API_KEY=your_dailymotion_api_key
   DAILYMOTION_API_SECRET=your_dailymotion_api_secret
   DAILYMOTION_USERNAME=your_dailymotion_username
   DAILYMOTION_PASSWORD=your_dailymotion_password
   ADMIN_IDS=1234567890,9876543210
   ADMIN_ONLY_MODE=true
   PORT=8080
   ```

6. **Advanced settings**:
   - Set the port to `8080`
   - Set the health check path to `/health`

7. **Deploy** the application.

### Option 2: Using the Koyeb CLI

1. **Install the Koyeb CLI**:
   ```bash
   curl -fsSL https://cli.koyeb.com/install.sh | sh
   ```

2. **Log in to your Koyeb account**:
   ```bash
   koyeb login
   ```

3. **Deploy using the koyeb.yaml file**:
   ```bash
   koyeb app init dailymotion-uploader-bot -f koyeb.yaml
   ```

4. **Create secrets for your credentials**:
   ```bash
   koyeb secret create api_id -v "your_telegram_api_id"
   koyeb secret create api_hash -v "your_telegram_api_hash"
   koyeb secret create bot_token -v "your_telegram_bot_token"
   koyeb secret create dailymotion_api_key -v "your_dailymotion_api_key"
   koyeb secret create dailymotion_api_secret -v "your_dailymotion_api_secret"
   koyeb secret create dailymotion_username -v "your_dailymotion_username"
   koyeb secret create dailymotion_password -v "your_dailymotion_password"
   koyeb secret create admin_ids -v "1234567890,9876543210"
   ```

5. **Follow the deployment status**:
   ```bash
   koyeb service get dailymotion-uploader-bot
   ```

## Monitoring and Maintenance

- Visit your Koyeb dashboard to monitor the application.
- Check the logs for any issues.
- The application has a health check endpoint at `/health` that will return the status of the bot.
- You can also check the status via the Telegram bot itself by sending the `/status` command.

## Troubleshooting

If you encounter any issues:

1. Check the application logs in the Koyeb dashboard.
2. Verify that all environment variables are correctly set.
3. Ensure your Telegram and Dailymotion credentials are valid.
4. Check if the health check endpoint is responding correctly.

For persistent issues, you can restart the service from the Koyeb dashboard or using the CLI:

```bash
koyeb service restart dailymotion-uploader-bot
```

## Advanced Configuration

For advanced configuration, you can modify:

- The number of worker processes in the Dockerfile
- Memory allocation in the Koyeb dashboard
- Storage configuration for temporary files

## Support

If you encounter any issues with the deployment, please:

1. Check the logs in the Koyeb dashboard
2. Refer to the Koyeb documentation: https://www.koyeb.com/docs
3. Open an issue in the GitHub repository