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
logger = logging.getLogger() # Root logger
logger.setLevel(logging.INFO) # Set root level

# Console Handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

# Optional: File Handler (configure path in .env or here)
# try:
#     file_handler = logging.FileHandler("bot_app.log")
#     file_handler.setFormatter(log_formatter)
#     logger.addHandler(file_handler)
# except Exception as e:
#     logger.error(f"Could not set up file logging: {e}")

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

    # Set logging level based on config if needed (e.g., add LOG_LEVEL to .env)
    # logger.setLevel(config.log_level)

    telegram_bot = TelegramBot(config)
    domain_checker = DomainChecker(config, telegram_bot.send_notification_to_admins)

    # Get the job queue from the bot's application
    job_queue = telegram_bot.application.job_queue

    # Schedule the domain checking job
    # `first=10` runs the first check 10 seconds after startup
    # `job_kwargs` can pass arguments if the job function needs them, not needed here
    job_queue.run_repeating(
        domain_checker.check_domains_job,
        interval=config.check_cycle,
        first=10, # Run shortly after start, then repeat
        name="Domain Check Cycle"
    )
    logger.info(f"Scheduled domain check job to run every {config.check_cycle} seconds.")

    # Setup bot command and message handlers
    telegram_bot.setup_handlers()

    # Run the bot and the job queue concurrently
    # run_polling() handles the asyncio loop management
    logger.info("Starting application components...")
    try:
        # Use run_polling which handles the main loop and shutdown gracefully
        await telegram_bot.application.initialize() # Initialize handlers, persistence etc.
        telegram_bot.load_admin_ids() # Load admin IDs after initialization

        # Potentially send a startup message to admins
        await telegram_bot.send_notification_to_admins("🚀 Bot started successfully!")
        await telegram_bot.application.start() # Start the bot logic (fetching updates etc)
        await telegram_bot.application.updater.start_polling() # Start polling loop
        logger.info("Bot polling and job queue started.")

        # Let's try the complex way for proper cleanup:
        stop_event = asyncio.Event()

        # Function to handle termination signals
        def signal_handler(sig, frame):
            logger.warning(f"Received signal {sig}. Initiating graceful shutdown...")
            stop_event.set()

        # Register signal handlers
        signal.signal(signal.SIGINT, signal_handler)  # Handle Ctrl+C
        signal.signal(signal.SIGTERM, signal_handler) # Handle termination request

        # Wait until a shutdown signal is received
        await stop_event.wait()

        logger.info("Shutdown signal received. Stopping components...")

    except Exception as e:
        logger.critical(f"An unexpected error occurred in the main loop: {e}", exc_info=True)
    finally:
        logger.info("Starting final cleanup...")
        # Stop polling and the application gracefully
        if telegram_bot.application.updater and telegram_bot.application.updater._running:
            await telegram_bot.application.updater.stop()
            logger.info("Telegram polling stopped.")
        if telegram_bot.application._initialized:
            await telegram_bot.application.stop()
            logger.info("Telegram application stopped.")
        await telegram_bot.application.shutdown() # Clean up resources like persistence
        logger.info("Telegram application shut down.")

        # Close the HTTP client
        await domain_checker.close_client()
        logger.info("Application cleanup finished.")


if __name__ == "__main__":
    # Ensure the log directory exists (handled in Config now)
    # log_dir = os.path.dirname("logs/unreachable_domains.log")
    # if log_dir and not os.path.exists(log_dir):
    #     os.makedirs(log_dir)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application terminated by KeyboardInterrupt.")
    except Exception as e:
        logger.critical(f"Application failed to run: {e}", exc_info=True)
        sys.exit(1)
    logger.info("Application exiting.")