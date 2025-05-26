# config.py
import os
import json
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

class ConfigError(Exception):
    """Custom exception for configuration errors."""
    pass

class Config:
    def __init__(self, env_file='.env'):
        load_dotenv(dotenv_path=env_file)
        logger.info(f"Loading configuration from {env_file}")
        self.retry_interval = 5
        self.telegram_bot_token = self._get_env_var('TELEGRAM_BOT_TOKEN')
        self.domains_api = self._get_env_var('DOMAINS_API')
        self.timeout = self._get_env_var('TIMEOUT', converter=int, default=30)
        self.check_cycle = self._get_env_var('CHECK_CYCLE', converter=int, default=600)
        self.max_failures = self._get_env_var('MAX_FAILURES', converter=int, default=3)
        self.log_file = self._get_env_var('LOG_FILE', default='unreachable_domains.log')

        self.admin_phone_numbers = self._get_env_var_as_list('ADMIN_PHONE_NUMBERS')
        # self.ignore_domains = self._get_env_var_as_list('IGNORE_DOMAINS') # REMOVE THIS LINE

        # Ensure log directory exists
        log_dir = os.path.dirname(self.log_file)
        if log_dir and not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir)
                logger.info(f"Created log directory: {log_dir}")
            except OSError as e:
                logger.error(f"Failed to create log directory {log_dir}: {e}")

    def _get_env_var(self, var_name, converter=str, default=None, required=True):
        value = os.getenv(var_name, default)
        if required and value is None:
            raise ConfigError(f"Missing required environment variable: {var_name}")
        if value is not None:
            try:
                return converter(value)
            except ValueError as e:
                 raise ConfigError(f"Invalid type for environment variable {var_name}: Expected {converter.__name__}. Error: {e}")
        return None

    def _get_env_var_as_list(self, var_name, required=True):
        value_str = os.getenv(var_name)
        if not value_str:
            if required:
                raise ConfigError(f"Missing required environment variable: {var_name}")
            else:
                return []
        try:
            parsed_list = json.loads(value_str)
            if not isinstance(parsed_list, list):
                raise ValueError("Parsed JSON is not a list")
            if var_name == 'ADMIN_PHONE_NUMBERS':
                return [self._normalize_phone(item) for item in parsed_list if isinstance(item, str)]
            else:
                return [item for item in parsed_list if isinstance(item, str)]
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Could not parse {var_name} as JSON ('{value_str}'). Falling back to comma separation. Error: {e}. Please use JSON format like '[\"item1\", \"item2\"]' in .env for reliability.")
            items = [item.strip() for item in value_str.split(',') if item.strip()]
            if var_name == 'ADMIN_PHONE_NUMBERS':
                return [self._normalize_phone(item) for item in items]
            else:
                return items

    def _normalize_phone(self, number: str) -> str:
        """Ensure phone number starts with +."""
        num = number.strip()
        if num.isdigit():
             logger.warning(f"Phone number '{number}' seems to be missing '+'. Add '+' in .env for clarity.")
             return num
        if not num.startswith('+'):
             return "+" + num
        return num

# Example usage (optional, for testing config loading)
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        config = Config()
        logger.info(f"Config loaded successfully:")
        logger.info(f"  Bot Token: {'*' * 5}{config.telegram_bot_token[-4:]}")
        logger.info(f"  Domains API: {config.domains_api}")
        logger.info(f"  Admin Numbers: {config.admin_phone_numbers}")
        # logger.info(f"  Ignore Domains: {config.ignore_domains}") # REMOVE OR COMMENT OUT THIS LINE
        logger.info(f"  Timeout: {config.timeout}")
        logger.info(f"  Check Cycle: {config.check_cycle}")
        logger.info(f"  Max Failures: {config.max_failures}")
        logger.info(f"  Log File: {config.log_file}")
    except ConfigError as e:
        logger.error(f"Configuration Error: {e}")