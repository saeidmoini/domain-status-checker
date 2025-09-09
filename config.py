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
        
        # Core Settings
        self.telegram_bot_token = self._get_env_var('TELEGRAM_BOT_TOKEN')
        self.domains_api = self._get_env_var('DOMAINS_API')
        self.admin_phone_numbers = self._get_env_var_as_list('ADMIN_PHONE_NUMBERS')
        self.wp_health_check_api_key = self._get_env_var('WP_HEALTH_CHECK_API_KEY', required=False, default=None)

        # Timing and Failure Settings
        self.timeout = self._get_env_var('TIMEOUT', converter=int, default=30)
        self.check_cycle = self._get_env_var('CHECK_CYCLE', converter=int, default=600)
        self.max_failures = self._get_env_var('MAX_FAILURES', converter=int, default=3)
        self.retry_interval = 5 # This is internal and not from .env, which is fine.

        # File Paths
        self.log_file = self._get_env_var('LOG_FILE', default='logs/unreachable_domains.log')
        self.ignored_domains_file = self._get_env_var('IGNORED_DOMAINS_FILE', default='ignored_domains.json')
        self.persistence_file = self._get_env_var('PERSISTENCE_FILE', default='bot_persistence.pkl')

        # Security
        self.verify_ssl = self._get_env_var('VERIFY_SSL', converter=self._to_bool, default=True)

        # Ensure log directory exists
        log_dir = os.path.dirname(self.log_file)
        if log_dir and not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir)
                logger.info(f"Created log directory: {log_dir}")
            except OSError as e:
                logger.error(f"Failed to create log directory {log_dir}: {e}")

    def _get_env_var(self, var_name, converter=str, default=None, required=True):
        value = os.getenv(var_name)
        
        if value is None:
            if required and default is None:
                raise ConfigError(f"Missing required environment variable: {var_name}")
            value = default

        if value is not None:
            try:
                return converter(value)
            except (ValueError, TypeError) as e:
                 raise ConfigError(f"Invalid type for environment variable {var_name}. Error: {e}")
        return value

    def _get_env_var_as_list(self, var_name, required=True):
        value_str = os.getenv(var_name)
        if not value_str:
            if required:
                raise ConfigError(f"Missing required environment variable: {var_name}")
                return []
        try:
            parsed_list = json.loads(value_str)
            if not isinstance(parsed_list, list):
                raise ValueError("Parsed JSON is not a list.")
            
            # Normalize phone numbers if the variable is ADMIN_PHONE_NUMBERS
            if var_name == 'ADMIN_PHONE_NUMBERS':
                return [self._normalize_phone(item) for item in parsed_list if isinstance(item, str)]
            
            return [str(item) for item in parsed_list]

        except (json.JSONDecodeError, ValueError) as e:
            raise ConfigError(
                f"Could not parse {var_name} as a JSON list from value: '{value_str}'. "
                f"Please use the format '[\"item1\", \"item2\"]' in your .env file. Error: {e}"
            )

    def _normalize_phone(self, number: str) -> str:
        """Ensure phone number starts with +."""
        num = str(number).strip()
        if num.isdigit():
             logger.warning(f"Phone number '{number}' seems to be missing '+'. Adding it for normalization.")
             return f"+{num}"
        if not num.startswith('+'):
             return f"+{num}"
        return num

    def _to_bool(self, value: str) -> bool:
        """Converts a string to a boolean, accepting 'true'/'false'."""
        if isinstance(value, bool):
            return value
        if value.lower() in ('true', '1', 't', 'y', 'yes'):
            return True
        elif value.lower() in ('false', '0', 'f', 'n', 'no'):
            return False
        else:
            raise ValueError(f"Could not convert string to boolean: {value}")

# Example usage (optional, for testing config loading)
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        config = Config()
        logger.info(f"Config loaded successfully:")
        logger.info(f"  Bot Token: {'*' * 5}{config.telegram_bot_token[-4:]}")
        logger.info(f"  Domains API: {config.domains_api}")
        logger.info(f"  Admin Numbers: {config.admin_phone_numbers}")
        logger.info(f"  Timeout: {config.timeout}")
        logger.info(f"  Check Cycle: {config.check_cycle}")
        logger.info(f"  Max Failures: {config.max_failures}")
        logger.info(f"  Log File: {config.log_file}")
        logger.info(f"  Ignored Domains File: {config.ignored_domains_file}")
        logger.info(f"  Persistence File: {config.persistence_file}")
        logger.info(f"  Verify SSL: {config.verify_ssl}")
        logger.info(f"  WP Health Check API Key: {'Set' if config.wp_health_check_api_key else 'Not Set'}")
    except ConfigError as e:
        logger.error(f"Configuration Error: {e}")