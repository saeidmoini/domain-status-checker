# bot.py
import logging
from typing import Set, List
import re
import json
import os # Add this import for os.path.exists
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ApplicationBuilder,
    PicklePersistence,
)
from telegram.constants import ParseMode

from config import Config

logger = logging.getLogger(__name__)

# Define states for the conversation flow
ADD_DOMAIN_STATE = 1
REMOVE_DOMAIN_STATE = 2

class TelegramBot:
    def __init__(self, config: Config):
        self.config = config
        persistence = PicklePersistence(filepath="bot_persistence.pkl")
        self.application = ApplicationBuilder().token(config.telegram_bot_token).persistence(persistence).build()

        self.admin_chat_ids: Set[int] = set()
        logger.info(f"Admin chat IDs initialized to empty in __init__.")

        self.ignored_domains_file = "ignored_domains.json"
        self.ignored_domains: Set[str] = self._load_ignored_domains()

        # State management for multi-step commands
        # Maps chat_id to the state (e.g., ADD_DOMAIN_STATE, REMOVE_DOMAIN_STATE)
        self.user_states: dict[int, int] = {}
        logger.info("Initialized user_states for conversation management.")

    def load_admin_ids(self):
        self.admin_chat_ids: Set[int] = self.application.bot_data.setdefault('admin_chat_ids', set())
        logger.info(f"Loaded {len(self.admin_chat_ids)} admin chat IDs from persistence (after init).")

    def _load_ignored_domains(self) -> Set[str]:
        """Loads ignored domains from a JSON file."""
        try:
            if os.path.exists(self.ignored_domains_file):
                with open(self.ignored_domains_file, 'r') as f:
                    domains = json.load(f)
                    if isinstance(domains, list):
                        logger.info(f"Loaded {len(domains)} ignored domains from {self.ignored_domains_file}.")
                        return set(domains)
            logger.info(f"No ignored domains file found or invalid format. Starting with empty list.")
            return set()
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from {self.ignored_domains_file}: {e}")
            return set()
        except Exception as e:
            logger.error(f"Error loading ignored domains from {self.ignored_domains_file}: {e}")
            return set()

    def _save_ignored_domains(self):
        """Saves ignored domains to a JSON file."""
        try:
            with open(self.ignored_domains_file, 'w') as f:
                json.dump(list(self.ignored_domains), f, indent=4)
            logger.info(f"Saved {len(self.ignored_domains)} ignored domains to {self.ignored_domains_file}.")
        except Exception as e:
            logger.error(f"Error saving ignored domains to {self.ignored_domains_file}: {e}")

    def get_current_ignored_domains(self) -> Set[str]:
        """Returns the current set of ignored domains from memory."""
        return self.ignored_domains

    def _normalize_phone(self, number: str) -> str:
        """Ensure phone number starts with + (basic normalization)."""
        num = number.strip()
        if num.isdigit():
            logger.warning(f"Phone number '{number}' seems to be missing '+'. Comparing as is, but add '+' in .env for robustness.")
            return num
        if not num.startswith('+'):
            return "+" + num
        return num

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles the /start command."""
        user = update.effective_user
        chat_id = update.effective_chat.id
        logger.info(f"Received /start command from user {user.id} ({user.username}) in chat {chat_id}")

        # Clear any ongoing state for this user
        if chat_id in self.user_states:
            del self.user_states[chat_id]
            await update.message.reply_text("Previous operation cancelled.")


        if chat_id in self.admin_chat_ids:
            await update.message.reply_text("Welcome back, Admin! You are already verified.")
            return

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

        if contact.user_id != user_id:
            logger.warning(f"Contact user ID ({contact.user_id}) does not match message sender ID ({user_id}). Ignoring.")
            await update.message.reply_text(
                "Verification failed. The contact shared does not seem to belong to you.",
                reply_markup=ReplyKeyboardRemove()
            )
            return

        phone_number = self._normalize_phone(contact.phone_number)
        logger.info(f"Normalized phone number: {phone_number}")

        if phone_number in self.config.admin_phone_numbers:
            logger.info(f"Phone number {phone_number} MATCHES admin list. Adding chat ID {chat_id} as admin.")
            self.admin_chat_ids.add(chat_id)
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
                    parse_mode=ParseMode.HTML
                )
                logger.debug(f"Sent notification successfully to chat_id: {chat_id}")
                sent_to += 1
            except Exception as e:
                logger.error(f"Failed to send notification to chat_id {chat_id}: {e}")
                failed_for += 1
        logger.info(f"Notification sending complete. Sent: {sent_to}, Failed: {failed_for}")

    async def _check_admin_permission(self, update: Update) -> bool:
        """Checks if the user sending the command is an admin."""
        chat_id = update.effective_chat.id
        if chat_id not in self.admin_chat_ids:
            await update.message.reply_text("You are not authorized to use this command. Please verify as admin first.")
            logger.warning(f"Unauthorized access attempt by user {update.effective_user.id} to admin command.")
            return False
        return True

    async def ignore_list_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Sends the list of ignored domains."""
        if not await self._check_admin_permission(update):
            return

        # Clear any ongoing state for this user
        chat_id = update.effective_chat.id
        if chat_id in self.user_states:
            del self.user_states[chat_id]
            await update.message.reply_text("Previous operation cancelled.")

        if not self.ignored_domains:
            await update.message.reply_text("The ignore list is currently empty.")
            return

        message = "<b>Ignored Domains:</b>\n" + "\n".join(f"- <code>{domain}</code>" for domain in sorted(list(self.ignored_domains)))
        await update.message.reply_text(message, parse_mode=ParseMode.HTML)
        logger.info(f"Sent ignore list to admin {update.effective_user.id}.")

    async def ignore_add_command_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Starts the process of adding a domain to the ignore list."""
        if not await self._check_admin_permission(update):
            return

        chat_id = update.effective_chat.id
        self.user_states[chat_id] = ADD_DOMAIN_STATE
        await update.message.reply_text("Please send the domain you wish to add to the ignore list (e.g., `example.com`).")
        logger.info(f"Admin {update.effective_user.id} initiated ignore_add command.")

    async def ignore_remove_command_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Starts the process of removing a domain from the ignore list."""
        if not await self._check_admin_permission(update):
            return

        chat_id = update.effective_chat.id
        self.user_states[chat_id] = REMOVE_DOMAIN_STATE
        await update.message.reply_text("Please send the domain you wish to remove from the ignore list (e.g., `example.com`).")
        logger.info(f"Admin {update.effective_user.id} initiated ignore_remove command.")

    async def handle_domain_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles the domain input based on the current user state."""
        chat_id = update.effective_chat.id
        user_state = self.user_states.get(chat_id)

        if not user_state:
            # If there's no active state, just ignore this message or provide a default response
            # await update.message.reply_text("I'm not expecting a domain right now. Use /ignore_add or /ignore_remove first.")
            logger.debug(f"Received unexpected message from {chat_id} with no active state.")
            return

        domain_input = update.message.text.strip().lower()

        # Basic validation for domain format (can be improved)
        if not re.match(r"^[a-z0-9-]+\.[a-z0-9-.]+$", domain_input):
            await update.message.reply_text(
                f"<code>{domain_input}</code> does not look like a valid domain format. Please try again or type /cancel to abort.",
                parse_mode=ParseMode.HTML
            )
            logger.warning(f"Invalid domain format received from {chat_id}: {domain_input}")
            return

        if user_state == ADD_DOMAIN_STATE:
            if domain_input in self.ignored_domains:
                await update.message.reply_text(f"Domain <code>{domain_input}</code> is already in the ignore list.", parse_mode=ParseMode.HTML)
            else:
                self.ignored_domains.add(domain_input)
                self._save_ignored_domains()
                await update.message.reply_text(f"Domain <code>{domain_input}</code> added to the ignore list.", parse_mode=ParseMode.HTML)
                logger.info(f"Admin {update.effective_user.id} added domain to ignore list: {domain_input}")
        elif user_state == REMOVE_DOMAIN_STATE:
            if domain_input not in self.ignored_domains:
                await update.message.reply_text(f"Domain <code>{domain_input}</code> is not in the ignore list.", parse_mode=ParseMode.HTML)
            else:
                self.ignored_domains.remove(domain_input)
                self._save_ignored_domains()
                await update.message.reply_text(f"Domain <code>{domain_input}</code> removed from the ignore list.", parse_mode=ParseMode.HTML)
                logger.info(f"Admin {update.effective_user.id} removed domain from ignore list: {domain_input}")

        # Clear the state after processing the domain
        del self.user_states[chat_id]
        logger.info(f"Cleared state for chat_id {chat_id} after processing domain '{domain_input}'.")

    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancels any ongoing conversation."""
        chat_id = update.effective_chat.id
        if chat_id in self.user_states:
            del self.user_states[chat_id]
            await update.message.reply_text("Operation cancelled.")
            logger.info(f"Admin {update.effective_user.id} cancelled an operation.")
        else:
            await update.message.reply_text("No active operation to cancel.")

    def setup_handlers(self):
        """Adds command and message handlers to the application."""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("cancel", self.cancel_command)) # New cancel command
        self.application.add_handler(MessageHandler(filters.CONTACT, self.contact_handler))

        self.application.add_handler(CommandHandler("ignore_list", self.ignore_list_command))
        self.application.add_handler(CommandHandler("ignore_add", self.ignore_add_command_start)) # Start the add flow
        self.application.add_handler(CommandHandler("ignore_remove", self.ignore_remove_command_start)) # Start the remove flow

        # This handler will catch any text message that is NOT a command
        # and will only proceed if the user has an active state.
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_domain_input))
        logger.info("Telegram handlers set up.")

    def run(self):
        """Starts the bot polling."""
        logger.info("Starting Telegram bot polling...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)
        logger.info("Telegram bot polling stopped.")