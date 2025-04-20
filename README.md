# Domain Status Checker

## Overview
Domain Status Checker is a Python-based tool that automates the process of checking the availability of domains retrieved from an API. It identifies unreachable domains and sends notifications to admins via Telegram. The tool also maintains a record of domain statuses for future reference.

## Features
- Fetches a list of domains from a JSON API.
- Checks the availability of each domain (HTTP status code < 400).
- Logs unreachable domains (HTTP status code >= 400).
- Sends Telegram notifications to admins for unreachable domains.
- Periodically runs the checks and updates the status records.
- Admin verification via phone number using Telegram bot.

## Requirements
- Python 3.8 or higher
- `requests` library
- `asyncio` library
- Access to an SMS API (e.g., Melipayamak)

## Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/domain-status-checker.git
   cd domain-status-checker
   ```
   
2. Install the required packages:
   ```bash
    pip install -r requirements.txt
    ```
3. Configure the `.env` file:

   Add the admin's phone numbers under ADMIN_PHONE_NUMBERS.
   Add the API endpoint that provides the list of domains under DOMAINS_API.
   Add the Telegram bot token under TELEGRAM_BOT_TOKEN.
   Add other configuration values as needed.
   Example .env file:

   DOMAINS_API="https://domains.irani-site.ir/"
   ADMIN_PHONE_NUMBERS=["+989105881921", "+989128008175"]
   IGNORE_DOMAINS=["irani-site.ir"]
   TELEGRAM_BOT_TOKEN="your-telegram-bot-token"
   TIMEOUT=15
   CHECK_CYCLE=60
   MAX_FAILURES=3
   LOG_FILE="logs/unreachable_domains.log"

5. Run the script:
```bash
    python run.py
 ```

## How It Works
Domain Checking:

The script fetches a list of domains from the API.
It checks the availability of each domain and logs unreachable ones.
Notifications are sent to admins via Telegram for unreachable domains.
Telegram Bot:

Admins verify themselves by sharing their phone numbers via the bot.
Verified admins receive notifications about domain statuses.
Logging:

Logs are stored in the file specified in the .env file under LOG_FILE.

### Project Structure
domain_checker.py: Contains the Checker class, which handles domain checking, configuration management, and notifications.
bot.py: Contains the TelegramBot class, which manages admin verification and notification delivery.
run.py: The entry point of the application. It initializes the Checker and TelegramBot classes and runs the periodic checks.
.env: Configuration file for environment variables.
requirements.txt: Lists all the dependencies required for the project.

## Contributions
Contributions are welcome! Please open an issue or submit a pull request for any improvements or bug fixes.

### Contact
For any questions or issues, please contact the repository owner.