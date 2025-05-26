# main.py
import asyncio
import logging
import signal
import sys
from config import Config, ConfigError
from domain_checker import DomainChecker
from bot import TelegramBot

# --- Logging Setup ---
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Console Handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)
logger.info("Logging configured")
# --- End Logging Setup ---


async def main():
    """Initializes and runs the application."""
    try:
        config = Config()
    except ConfigError as e:
        logger.critical(f"Configuration Error: {e}. Exiting.")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"Unexpected error loading configuration: {e}. Exiting.")
        sys.exit(1)


    telegram_bot = TelegramBot(config)
    # Pass the method to get ignored domains from the bot to the domain checker
    domain_checker = DomainChecker(config, telegram_bot.send_notification_to_admins, telegram_bot.get_current_ignored_domains)

    job_queue = telegram_bot.application.job_queue

    job_queue.run_repeating(
        domain_checker.check_domains_job,
        interval=config.check_cycle,
        first=10,
        name="Domain Check Cycle"
    )
    logger.info(f"Scheduled domain check job to run every {config.check_cycle} seconds.")

    telegram_bot.setup_handlers()

    logger.info("Starting application components...")
    try:
        await telegram_bot.application.initialize()
        telegram_bot.load_admin_ids()

        await telegram_bot.send_notification_to_admins("🚀 Bot started successfully!")
        await telegram_bot.application.start()
        await telegram_bot.application.updater.start_polling()
        logger.info("Bot polling and job queue started.")

        stop_event = asyncio.Event()

        def signal_handler(sig, frame):
            logger.warning(f"Received signal {sig}. Initiating graceful shutdown...")
            stop_event.set()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        await stop_event.wait()

        logger.info("Shutdown signal received. Stopping components...")

    except Exception as e:
        logger.critical(f"An unexpected error occurred in the main loop: {e}", exc_info=True)
    finally:
        logger.info("Starting final cleanup...")
        if telegram_bot.application.updater and telegram_bot.application.updater._running:
            await telegram_bot.application.updater.stop()
            logger.info("Telegram polling stopped.")
        if telegram_bot.application._initialized:
            await telegram_bot.application.stop()
            logger.info("Telegram application stopped.")
        await telegram_bot.application.shutdown()
        logger.info("Telegram application shut down.")

        await domain_checker.close_client()
        logger.info("Application cleanup finished.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application terminated by KeyboardInterrupt.")
    except Exception as e:
        logger.critical(f"Application failed to run: {e}", exc_info=True)
        sys.exit(1)
    logger.info("Application exiting.")