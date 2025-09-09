# WordPress Site Health Monitor Bot

A comprehensive Telegram bot for monitoring the health and uptime of multiple WordPress websites, providing instant notifications for any issues.

## Why This Project?

As a web developer managing numerous WordPress sites, it's challenging to manually check each site 24/7 to ensure it's online and functioning correctly. A site could be "up" (returning a 200 status code) but still have critical backend issues (e.g., a broken theme or plugin).

This bot was created to solve that problem. It not only checks if a site is reachable but also verifies the health of the WordPress application itself, providing instant alerts via Telegram the moment a problem is detected.

## Key Features

- **Multi-Domain Monitoring**: Fetches a list of domains from a dynamic API endpoint.
- **Dual-Layer Health Check**:
    1.  Checks the domain's root HTTP status.
    2.  If the site is up, it queries a dedicated WordPress health check endpoint to ensure the application is healthy.
- **Instant Telegram Alerts**: Sends immediate notifications to authorized admins when a site becomes unreachable or recovers.
- **Smart Retries**: Implements a retry mechanism to avoid false positives from temporary network glitches.
- **Admin Verification**: Securely verifies admins via their phone numbers.
- **Interactive Bot Commands**: Admins can list, add, or remove domains from an ignore list directly through the bot.
- **Persistent State**: Remembers admin users and ignored domains even after restarts.
- **Graceful Shutdown & Startup**: Handles server restarts and signals properly.

## Architecture Overview

```
+-----------------+      +----------------------+      +---------------------+
|   Domains API   |----->|  Python Monitor Bot  |<-----|   WordPress Sites   |
| (Your Endpoint) |      | (This Application)   |      | (with Health Plugin)|
+-----------------+      +----------------------+      +---------------------+
        ^                        |
        |                        | (Notifications)
        |                        |
        v                        v
+-----------------+      +----------------------+
|  Your Database  |      |   Telegram Admins    |
|   or CMS with   |      |                      |
| a list of sites |      +----------------------+
+-----------------+
```

## Prerequisites

- Python 3.8+
- An active Telegram account
- A Telegram Bot Token (get one from [@BotFather](https://t.me/BotFather))

## Installation & Setup

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/saeidmoini/domain-status-checker.git
    cd your-repo-name
    ```

2.  **Create a virtual environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install the required dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set up your configuration:**
    -   Rename the example environment file:
        ```bash
        mv .env.example .env
        ```
    -   Edit the `.env` file with your favorite editor (e.g., `nano .env`) and fill in your details.

## Configuration (`.env` file)

| Variable                  | Description                                                                                                                              | Example                                        |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------- |
| `TELEGRAM_BOT_TOKEN`      | Your unique token from Telegram's @BotFather.                                                                                            | `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`    |
| `ADMIN_PHONE_NUMBERS`     | A JSON-formatted list of admin phone numbers in international format. These users will receive alerts.                                   | `["+15551234567", "+442071234567"]`             |
| `DOMAINS_API`             | The API endpoint that returns a JSON list of domains to monitor.                                                                         | `https://api.example.com/sites`                |
| `WP_HEALTH_CHECK_API_KEY` | (Optional) The API key to access the WordPress health check endpoint.                                                                    | `your-secret-api-key`                          |
| `CHECK_CYCLE`             | How often the bot checks all domains, in seconds.                                                                                        | `600` (for 10 minutes)                         |
| `MAX_FAILURES`            | How many times to retry a failed domain check before marking it as down.                                                                 | `3`                                            |
| `TIMEOUT`                 | The timeout for HTTP requests in seconds.                                                                                                | `30`                                           |
| `LOG_FILE`                | Path to the log file for unreachable domains.                                                                                            | `logs/unreachable_domains.log`                 |
| `IGNORED_DOMAINS_FILE`    | Path to the JSON file where ignored domains are stored.                                                                                  | `ignored_domains.json`                         |
| `PERSISTENCE_FILE`        | Path to the file for storing the bot's persistent data (like admin IDs).                                                                 | `bot_persistence.pkl`                          |
| `VERIFY_SSL`              | `true` or `false`. Set to `false` to disable SSL certificate verification. **Warning**: This is a security risk.                           | `true`                                         |

## WordPress Setup

For the WordPress-specific health check to work, you need to set up an endpoint on each of your sites.

1.  **Install a Health Check Plugin**:
    A simple way is to use a plugin that creates a secure API endpoint. A good choice is the **"WP Health Check API"** plugin or you can create your own.

2.  **Create the Endpoint**:
    Your endpoint should be accessible at:
    `https://example.com/wp-json/wp-health-check/v1/status`

3.  **Secure the Endpoint**:
    The endpoint should be protected by an API key. This is the key you will put in the `WP_HEALTH_CHECK_API_KEY` variable in your `.env` file.

4.  **Expected Response**:
    When the endpoint is called with a valid API key, it should return a JSON response like this for a healthy site:
    ```json
    {
      "status": "ok",
      "message": "WordPress is healthy"
    }
    ```
    If there is an issue, the `status` should be something other than `ok`.

## Running the Bot

Once your configuration is complete, you can run the bot:

```bash
python3 main.py
```

To keep the bot running in the background, it is recommended to use a process manager like `systemd` or `supervisor`.

## Bot Usage & Commands

Interact with your bot on Telegram.

-   `/start` - The first command to run. It will prompt you to share your contact to verify you as an admin.
-   `/ignore_list` - Shows the list of domains that are currently excluded from monitoring.
-   `/ignore_add` - Starts a conversation to add a new domain to the ignore list.
-   `/ignore_remove` - Starts a conversation to remove a domain from the ignore list.
-   `/restart_checker` - Manually forces the domain checker to restart its cycle immediately. This is useful after you've fixed a site and want to confirm it's back online right away.
-   `/cancel` - Cancels the current multi-step operation (like adding/removing an ignored domain).
