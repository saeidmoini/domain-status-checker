# domain_checker.py
import asyncio
import logging
import httpx
import time
import json # Ensure json is imported
from typing import Callable, Awaitable, Set, Dict, List
from contextlib import asynccontextmanager
from config import Config

logger = logging.getLogger(__name__)

class DomainChecker:
    def __init__(self, config: Config, notifier: Callable[[str], Awaitable[None]], get_ignored_domains: Callable[[], Set[str]]):
        self.config = config
        self.notifier = notifier
        self.get_ignored_domains = get_ignored_domains
        self.log_file_path = config.log_file

        self._client = httpx.AsyncClient(
            timeout=self.config.timeout,
            follow_redirects=True,
            verify=False
        )
        self.last_api_failure = None
        self.api_failure_notified = False
        logger.info(f"HTTP Client initialized with timeout={self.config.timeout}s")

        self.stop_event = asyncio.Event()
        self.reset_state()

    def reset_state(self):
        logger.info("Resetting DomainChecker state: failure_counts and unreachable_domains.")
        self.failure_counts: Dict[str, int] = {}
        self.unreachable_domains: Set[str] = set()
        self.stop_event.clear()

    async def close_client(self):
        await self._client.aclose()
        logger.info("HTTP Client closed.")

    async def fetch_domains(self) -> List[str]:
        """Fetches the list of domains from the configured API."""
        logger.debug(f"Fetching domains from {self.config.domains_api}")
        try:
            response = await self._client.get(self.config.domains_api)
            response.raise_for_status()
            domains = response.json()
            # API is back online, if we previously had a failure, send recovery notification
            if self.api_failure_notified:
                await self.notifier("✅ Domains API is back online!")
                self.api_failure_notified = False
                self.last_api_failure = None
                
            if isinstance(domains, list) and all(isinstance(d, str) for d in domains):
                logger.info(f"Fetched {len(domains)} domains successfully.")
                return domains
            else:
                await self._handle_api_failure("Invalid format received from domain API")
                return []
                
        except httpx.RequestError as e:
            error_msg = f"❌ Domain API Error: {str(e)}\nAPI URL: {self.config.domains_api}"
            logger.error(error_msg)
            # Notify admins but don't spam them
            if not self.api_failure_notified:
                await self.notifier(error_msg)
                self.api_failure_notified = True
            return []
        except Exception as e:
            error_msg = f"❌ Unexpected error accessing Domain API: {str(e)}"
            logger.error(error_msg)
            if not self.api_failure_notified:
                await self.notifier(error_msg)
                self.api_failure_notified = True
            return []

    async def _handle_api_failure(self, error_message: str):
        """Handle API failure and send notification if needed."""
        current_time = time.time()
        
        # If this is the first failure or if it's been more than 15 minutes since last notification
        if (not self.last_api_failure or 
            not self.api_failure_notified or 
            current_time - self.last_api_failure > 900):  # 900 seconds = 15 minutes
            
            await self.notifier(
                f"⚠️ WARNING: Domains API is unreachable!\n"
                f"Error: {error_message}\n"
                f"URL: {self.config.domains_api}"
            )
            self.api_failure_notified = True
            self.last_api_failure = current_time
            logger.error(f"Domains API unreachable: {error_message}")
    def filter_domains(self, domains: List[str]) -> List[str]:
        """Filters out ignored domains."""
        ignored_set = self.get_ignored_domains()
        filtered = [d for d in domains if d not in ignored_set]
        if len(ignored_set) > 0:
             logger.debug(f"Filtered out {len(domains) - len(filtered)} ignored domains.")
        return filtered

    async def check_domain_status(self, domain: str) -> bool:
        """
        First checks the root domain's HTTP status. If it's 200, then checks the WordPress health endpoint.
        """
        api_key_param = f"?api_key={self.config.wp_health_check_api_key}" if self.config.wp_health_check_api_key else ""
        health_check_path = "/wp-json/wp-health-check/v1/status"

        # --- First, check the root domain's HTTP status ---
        urls_to_try_root = [f"https://{domain}", f"http://{domain}"]
        root_domain_is_200 = False

        for url in urls_to_try_root:
            if self.stop_event.is_set():
                logger.info(f"Stop signal received. Aborting check for {domain}.")
                return False

            logger.debug(f"Checking root domain {domain} via {url} for initial HTTP status.")
            try:
                response = await self._client.get(url)
                if response.status_code < 400:
                    logger.debug(f"Root domain {domain} ({url}) returned HTTP {response.status_code}. Proceeding to health check.")
                    root_domain_is_200 = True
                    break # Found a 200, proceed to health check
                else: # 4xx or 5xx status
                    logger.warning(f"Root domain {domain} ({url}) returned server error (Status: {response.status_code}). Treating as failure.")
                    return False # Server error, consider it down.
            except httpx.TimeoutException:
                logger.warning(f"Root domain {domain} ({url}) timed out after {self.config.timeout}s. Treating as failure.")
                return False
            except httpx.RequestError as e:
                logger.warning(f"Error checking root domain {domain} ({url}): {e}. Treating as failure.")
                return False
            except Exception as e:
                logger.error(f"Unexpected error checking root domain {domain} ({url}): {e}. Treating as failure.")
                return False

        if not root_domain_is_200:
            logger.info(f"Root domain {domain} did not return HTTP 200. Skipping WP health check.")
            return False # Already determined as unreachable if not 200

        # --- If root domain is 200, proceed to WordPress Health Check Endpoint ---
        logger.debug(f"Root domain {domain} is HTTP 200. Now attempting WP Health Check endpoint.")
        urls_to_try_health = [f"https://{domain}{health_check_path}{api_key_param}",
                              f"http://{domain}{health_check_path}{api_key_param}"]

        for url in urls_to_try_health:
            if self.stop_event.is_set():
                logger.info(f"Stop signal received. Aborting check for {domain}.")
                return False

            logger.debug(f"Checking WP Health Check endpoint {domain} via {url}")
            try:
                response = await self._client.get(url)

                if response.status_code == 200:
                    try:
                        health_data = response.json()
                        if health_data.get('status') == 'ok':
                            logger.debug(f"Domain {domain} ({url}) reported OK status from health endpoint.")
                            return True # Health check passed
                        else:
                            error_message = health_data.get('message', 'Unknown error from health endpoint.')
                            logger.warning(f"Domain {domain} ({url}) health endpoint reported an ERROR: {error_message}. Treating as failure.")
                            return False # Plugin reported an error
                    except json.JSONDecodeError:
                        logger.warning(f"Health endpoint {domain} ({url}) returned status 200 but not valid JSON. Treating as failure.")
                        return False
                elif response.status_code == 401:
                    logger.warning(f"Health endpoint {domain} ({url}) returned 401 Unauthorized. Check API key in plugin/config.")
                    return False # API key issue, treat as failure for health check.
                elif response.status_code >= 400:
                    logger.warning(f"Health endpoint {domain} ({url}) returned server error (Status: {response.status_code}). Treating as failure.")
                    return False
            except httpx.TimeoutException:
                logger.warning(f"Health endpoint {domain} ({url}) timed out after {self.config.timeout}s. Treating as failure.")
                return False
            except httpx.RequestError as e:
                logger.warning(f"Error checking health endpoint {domain} ({url}): {e}. Treating as failure.")
                return False
            except Exception as e:
                logger.error(f"Unexpected error checking health endpoint {domain} ({url}): {e}. Treating as failure.")
                return False

        # If we reach here, it means the root domain was 200, but the health check endpoint failed for some reason.
        logger.warning(f"WP Health Check endpoint for {domain} failed after root domain returned 200.")
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
        if self.stop_event.is_set():
            logger.info("check_domains_job received stop signal before starting. Aborting this run.")
            return

        logger.info("Starting domain check cycle with immediate retries...")
        start_time = time.monotonic()

        domains_to_check = self.filter_domains(await self.fetch_domains())
        if not domains_to_check:
            logger.warning("No domains to check in this cycle.")
            return

        logger.info(f"Checking status for {len(domains_to_check)} domains (initial check)...")

        tasks = [self.check_domain_status(domain) for domain in domains_to_check]
        initial_results = await asyncio.gather(*tasks, return_exceptions=True)

        if self.stop_event.is_set():
            logger.info("Stop signal received during initial check processing. Aborting this run.")
            return

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

        # Convert to list to allow modification of dict during iteration if needed,
        # though `del` on `failed_domains_for_retry` won't affect `list(keys())`
        for domain, failure_count in list(failed_domains_for_retry.items()):
            # Check for stop signal before each retry loop
            if self.stop_event.is_set():
                logger.info("Stop signal received during retries. Aborting remaining retries.")
                break

            while self.failure_counts.get(domain, 0) < self.config.max_failures and domain in current_domains_set:
                if self.stop_event.is_set():
                    logger.info(f"Stop signal received during retry loop for {domain}. Aborting this domain's retries.")
                    break

                logger.info(f"Retrying domain {domain} (Attempt #{self.failure_counts.get(domain, 0) + 1})...")
                # Add a small delay for the stop signal to be processed
                try:
                    await asyncio.sleep(self.config.retry_interval)
                except asyncio.CancelledError:
                    logger.info(f"Retry sleep for {domain} cancelled due to stop signal.")
                    break # Break out of inner while loop

                status_ok = await self.check_domain_status(domain)

                if self.stop_event.is_set(): # Check again after `check_domain_status`
                    logger.info(f"Stop signal received after check_domain_status for {domain}. Aborting.")
                    break

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

        if notification_message and not self.stop_event.is_set(): # Only notify if not stopped
            try:
                await self.notifier(notification_message.strip())
            except Exception as e:
                logger.error(f"Failed to send notification via callback: {e}")

        end_time = time.monotonic()
        if not self.stop_event.is_set():
            logger.info(
                f"Domain check cycle finished in {end_time - start_time:.2f} seconds. Total unreachable: {len(self.unreachable_domains)}. Next check in {self.config.check_cycle}s.")
        else:
            logger.info(f"Domain check cycle interrupted by stop signal after {end_time - start_time:.2f} seconds.")