# domain_checker.py
import asyncio
import logging
import httpx
import time
from typing import Callable, Awaitable, Set, Dict, List
from contextlib import asynccontextmanager
from config import Config

logger = logging.getLogger(__name__)

class DomainChecker:
    def __init__(self, config: Config, notifier: Callable[[str], Awaitable[None]], get_ignored_domains: Callable[[], Set[str]]): # Added get_ignored_domains
        self.config = config
        self.notifier = notifier
        self.get_ignored_domains = get_ignored_domains # New: Function to get current ignored domains
        self.failure_counts: Dict[str, int] = {}
        self.unreachable_domains: Set[str] = set()
        self.log_file_path = config.log_file

        self._client = httpx.AsyncClient(
            timeout=self.config.timeout,
            follow_redirects=True,
            verify=False
        )
        logger.info(f"HTTP Client initialized with timeout={self.config.timeout}s")

    async def close_client(self):
        """Gracefully close the HTTP client."""
        await self._client.aclose()
        logger.info("HTTP Client closed.")

    async def fetch_domains(self) -> List[str]:
        """Fetches the list of domains from the configured API."""
        logger.debug(f"Fetching domains from {self.config.domains_api}")
        try:
            response = await self._client.get(self.config.domains_api)
            response.raise_for_status()
            domains = response.json()
            if isinstance(domains, list) and all(isinstance(d, str) for d in domains):
                logger.info(f"Fetched {len(domains)} domains successfully.")
                return domains
            else:
                logger.error(f"Invalid format received from domain API. Expected list of strings, got: {type(domains)}")
                return []
        except httpx.RequestError as e:
            logger.error(f"HTTP error fetching domains from {self.config.domains_api}: {e}")
            return []
        except Exception as e:
            logger.error(f"Error processing domains response from {self.config.domains_api}: {e}")
            return []

    def filter_domains(self, domains: List[str]) -> List[str]:
        """Filters out ignored domains."""
        # Get the current ignored domains from the bot instance
        ignored_set = self.get_ignored_domains() # Use the getter function
        filtered = [d for d in domains if d not in ignored_set]
        if len(ignored_set) > 0:
             logger.debug(f"Filtered out {len(domains) - len(filtered)} ignored domains.")
        return filtered

    async def check_domain_status(self, domain: str) -> bool:
        """Checks if a domain is reachable via HTTP(S) GET."""
        urls_to_try = [f"https://{domain}", f"http://{domain}"]
        for url in urls_to_try:
            logger.debug(f"Checking domain {domain} via {url}")
            try:
                response = await self._client.get(url)
                if response.status_code < 400:
                    logger.debug(f"Domain {domain} ({url}) is reachable (Status: {response.status_code}).")
                    return True
                else:
                    logger.warning(f"Domain {domain} ({url}) returned server error (Status: {response.status_code}). Treating as failure.")
            except httpx.TimeoutException:
                logger.warning(f"Domain {domain} ({url}) timed out after {self.config.timeout}s.")
            except httpx.RequestError as e:
                logger.warning(f"Error checking domain {domain} ({url}): {e}")
            except Exception as e:
                 logger.error(f"Unexpected error checking domain {domain} ({url}): {e}")

        logger.warning(f"Domain {domain} failed all checks (HTTPS/HTTP).")
        return False

    def _log_unreachable(self, domain: str):
        """Logs newly unreachable domain to a file."""
        try:
            with open(self.log_file_path, 'a') as f:
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S %Z")
                f.write(f"{timestamp} - UNREACHABLE: {domain}\n")
            logger.info(f"Logged unreachable domain to {self.log_file_path}: {domain}")
        except IOError as e:
            logger.error(f"Failed to write to log file {self.log_file_path}: {e}")

    def _log_reachable(self, domain: str):
        """Logs domain becoming reachable again to a file."""
        try:
            with open(self.log_file_path, 'a') as f:
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S %Z")
                f.write(f"{timestamp} - REACHABLE: {domain}\n")
            logger.info(f"Logged reachable domain to {self.log_file_path}: {domain}")
        except IOError as e:
            logger.error(f"Failed to write to log file {self.log_file_path}: {e}")

    async def check_domains_job(self, context=None):
        """The main job executed periodically with immediate retries for failures."""
        logger.info("Starting domain check cycle with immediate retries...")
        start_time = time.monotonic()

        domains_to_check = self.filter_domains(await self.fetch_domains())
        if not domains_to_check:
            logger.warning("No domains to check in this cycle.")
            return

        logger.info(f"Checking status for {len(domains_to_check)} domains (initial check)...")

        tasks = [self.check_domain_status(domain) for domain in domains_to_check]
        initial_results = await asyncio.gather(*tasks, return_exceptions=True)

        newly_unreachable = []
        newly_reachable = []
        current_domains_set = set(domains_to_check)
        failed_domains_for_retry = {}

        for domain, result in zip(domains_to_check, initial_results):
            if isinstance(result, Exception):
                logger.error(f"Exception during initial check for {domain}: {result}")
                status_ok = False
            else:
                status_ok = result

            if status_ok:
                if domain in self.unreachable_domains:
                    logger.info(f"Domain {domain} is now REACHABLE.")
                    self.unreachable_domains.remove(domain)
                    newly_reachable.append(domain)
                    self._log_reachable(domain)
                if domain in self.failure_counts:
                    del self.failure_counts[domain]
            else:
                self.failure_counts[domain] = self.failure_counts.get(domain, 0) + 1
                logger.warning(f"Domain {domain} failed initial check #{self.failure_counts[domain]}.")
                if self.failure_counts[domain] < self.config.max_failures:
                    failed_domains_for_retry[domain] = self.failure_counts[domain]

        logger.info("Starting immediate retries for failed domains...")

        for domain, failure_count in list(failed_domains_for_retry.items()):
            while self.failure_counts.get(domain, 0) < self.config.max_failures and domain in current_domains_set:
                logger.info(f"Retrying domain {domain} (Attempt #{self.failure_counts.get(domain, 0) + 1})...")
                await asyncio.sleep(self.config.retry_interval)
                status_ok = await self.check_domain_status(domain)

                if status_ok:
                    logger.info(f"Domain {domain} became reachable after retry.")
                    if domain in self.unreachable_domains:
                        self.unreachable_domains.remove(domain)
                        newly_reachable.append(domain)
                        self._log_reachable(domain)
                    if domain in self.failure_counts:
                        del self.failure_counts[domain]
                    if domain in failed_domains_for_retry:
                        del failed_domains_for_retry[domain]
                    break
                else:
                    self.failure_counts[domain] = self.failure_counts.get(domain, 0) + 1
                    logger.warning(f"Domain {domain} failed retry #{self.failure_counts[domain]}.")
                    if self.failure_counts[
                        domain] >= self.config.max_failures and domain not in self.unreachable_domains:
                        logger.error(
                            f"Domain {domain} has reached {self.failure_counts[domain]} failures. Marking as UNREACHABLE after retries.")
                        self.unreachable_domains.add(domain)
                        newly_unreachable.append(domain)
                        self._log_unreachable(domain)
                        if domain in failed_domains_for_retry:
                            del failed_domains_for_retry[domain]

        stale_domains = set(self.failure_counts.keys()) - current_domains_set
        if stale_domains:
            logger.debug(f"Removing stale domains from failure counts: {stale_domains}")
            for domain in stale_domains:
                del self.failure_counts[domain]
                if domain in self.unreachable_domains:
                    logger.info(f"Domain {domain} removed from source list, also removing from unreachable list.")
                    self.unreachable_domains.remove(domain)

        notification_message = ""
        if newly_unreachable:
            notification_message += f"🔴 Newly UNREACHABLE Domains:\n - " + "\n - ".join(newly_unreachable) + "\n\n"
            logger.warning(f"Domains newly marked as unreachable: {newly_unreachable}")

        if newly_reachable:
            notification_message += f"✅ Newly REACHABLE Domains:\n - " + "\n - ".join(newly_reachable)
            logger.info(f"Domains newly marked as reachable: {newly_reachable}")

        if notification_message:
            try:
                await self.notifier(notification_message.strip())
            except Exception as e:
                logger.error(f"Failed to send notification via callback: {e}")

        end_time = time.monotonic()
        logger.info(
            f"Domain check cycle finished in {end_time - start_time:.2f} seconds. Total unreachable: {len(self.unreachable_domains)}. Next check in {self.config.check_cycle}s.")