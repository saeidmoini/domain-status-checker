# bot.py
import logging
from typing import Set
import re
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ApplicationBuilder,
    PicklePersistence, # Optional: for persisting admin list across restarts
)
from telegram.constants import ParseMode

from config import Config

logger = logging.getLogger(__name__)

class TelegramBot:
    def __init__(self, config: Config):
        self.config = config
        # Using PicklePersistence to remember admins across restarts
        # Change 'bot_persistence.pkl' filename/path as needed
        persistence = PicklePersistence(filepath="bot_persistence.pkl")
        self.application = ApplicationBuilder().token(config.telegram_bot_token).persistence(persistence).build()

        # Initialize admin chat IDs to empty
        self.admin_chat_ids: Set[int] = set()
        logger.info(f"Admin chat IDs initialized to empty in __init__.")

    def load_admin_ids(self):
        self.admin_chat_ids: Set[int] = self.application.bot_data.setdefault('admin_chat_ids', set())
        logger.info(f"Loaded {len(self.admin_chat_ids)} admin chat IDs from persistence (after init).")

    def _normalize_phone(self, number: str) -> str:
        """Ensure phone number starts with + (basic normalization)."""
        num = number.strip()
        if num.isdigit(): # Simple check if it's just digits
            logger.warning(f"Phone number '{number}' seems to be missing '+'. Comparing as is, but add '+' in .env for robustness.")
            return num # Return as is, comparison relies on .env format matching
        if not num.startswith('+'):
            return "+" + num
        return num

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles the /start command."""
        user = update.effective_user
        chat_id = update.effective_chat.id
        logger.info(f"Received /start command from user {user.id} ({user.username}) in chat {chat_id}")

        if chat_id in self.admin_chat_ids:
            await update.message.reply_text("Welcome back, Admin! You are already verified.")
            return

        # Ask for contact
        keyboard = [
            [KeyboardButton("Share My Contact", request_contact=True)]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

        await update.message.reply_text(
            "Welcome! To verify if you are an admin, please share your contact information using the button below.",
            reply_markup=reply_markup
        )

    async def contact_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles receiving contact information."""
        contact = update.message.contact
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id

        logger.info(f"Received contact from user {user_id} in chat {chat_id}")

        # Security check: Ensure the contact shared belongs to the user sending it
        if contact.user_id != user_id:
            logger.warning(f"Contact user ID ({contact.user_id}) does not match message sender ID ({user_id}). Ignoring.")
            await update.message.reply_text(
                "Verification failed. The contact shared does not seem to belong to you.",
                reply_markup=ReplyKeyboardRemove()
            )
            return

        phone_number = self._normalize_phone(contact.phone_number)
        logger.info(f"Normalized phone number: {phone_number}")

        # Check against admin list from config
        if phone_number in self.config.admin_phone_numbers:
            logger.info(f"Phone number {phone_number} MATCHES admin list. Adding chat ID {chat_id} as admin.")
            self.admin_chat_ids.add(chat_id)
            # Save updated admin list to persistence
            context.bot_data['admin_chat_ids'] = self.admin_chat_ids
            await context.application.persistence.update_bot_data(context.bot_data)

            await update.message.reply_text(
                "✅ Verification successful! You are now registered as an admin and will receive alerts.",
                reply_markup=ReplyKeyboardRemove()
            )
        else:
            logger.warning(f"Phone number {phone_number} does NOT match admin list.")
            await update.message.reply_text(
                "❌ Verification failed. Your phone number is not registered in the admin list.",
                reply_markup=ReplyKeyboardRemove()
            )

    async def send_notification_to_admins(self, message: str):
        """Sends a message to all verified admin chats."""
        if not self.admin_chat_ids:
            logger.warning("Tried to send notification, but no admin users are registered.")
            return

        logger.info(f"Sending notification to {len(self.admin_chat_ids)} admin(s).")
        sent_to = 0
        failed_for = 0
        for chat_id in self.admin_chat_ids:
            try:
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode=ParseMode.HTML # Or MARKDOWN_V2 if you prefer
                )
                logger.debug(f"Sent notification successfully to chat_id: {chat_id}")
                sent_to += 1
            except Exception as e:
                logger.error(f"Failed to send notification to chat_id {chat_id}: {e}")
                failed_for += 1
                # Optional: Consider removing chat_id if it consistently fails (e.g., bot blocked)
        logger.info(f"Notification sending complete. Sent: {sent_to}, Failed: {failed_for}")

    def setup_handlers(self):
        """Adds command and message handlers to the application."""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(MessageHandler(filters.CONTACT, self.contact_handler))
        logger.info("Telegram handlers set up.")

    def run(self):
        """Starts the bot polling."""
        logger.info("Starting Telegram bot polling...")
        # run_polling blocks until interrupted (e.g., Ctrl+C)
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)
        logger.info("Telegram bot polling stopped.")