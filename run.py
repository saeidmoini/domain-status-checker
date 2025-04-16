import os

from main import Checker
import asyncio
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

DOMAINS_API = os.getenv("DOMAINS_API")
TIMEOUT = 60
SLEEP_TIME = 3600  # 1 hour
CONFIG_ADDRESS = ".config"
NUMBER_OF_ALLOWED_ERRORS = 3

async def main():
    ERROR_REAPEAT = 0
    checker = Checker(config_file=CONFIG_ADDRESS, domains_api=DOMAINS_API, timeout=TIMEOUT, sms=True)
    while True:
        try:
            await checker.run()
            ERROR_REAPEAT = 0
        except:
            ERROR_REAPEAT += 1
            if ERROR_REAPEAT == NUMBER_OF_ALLOWED_ERRORS:
                ERROR_REAPEAT = 0
                checker.send_SMS("Error : the program has an error and has been stopped")
            continue
        await asyncio.sleep(SLEEP_TIME)

if __name__ == "__main__":
    asyncio.run(main())