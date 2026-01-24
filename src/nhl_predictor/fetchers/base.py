"""Base fetcher class with common functionality."""

import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..models.database import get_db
from ..models.schema import DataFetchLog

logger = logging.getLogger(__name__)


class BaseFetcher(ABC):
    """Base class for all data fetchers with retry logic and logging."""

    # Default configuration
    MAX_RETRIES = 3
    RETRY_BACKOFF = 2  # Exponential backoff factor (2s, 4s, 8s)
    REQUEST_TIMEOUT = 30  # seconds
    RATE_LIMIT_DELAY = 2  # seconds between requests

    def __init__(self, source_name: str):
        """
        Initialize the fetcher.

        Args:
            source_name: Name of the data source for logging.
        """
        self.source_name = source_name
        self.session = self._create_session()
        self._last_request_time: Optional[float] = None

    def _create_session(self) -> requests.Session:
        """Create a requests session with retry logic."""
        session = requests.Session()

        # Configure retry strategy
        retry_strategy = Retry(
            total=self.MAX_RETRIES,
            backoff_factor=self.RETRY_BACKOFF,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # Set common headers
        session.headers.update({
            "User-Agent": "NHL-Predictor/1.0 (https://github.com/nhl-predictor)",
            "Accept": "application/json, text/html, */*",
        })

        return session

    def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        if self._last_request_time is not None:
            elapsed = time.time() - self._last_request_time
            if elapsed < self.RATE_LIMIT_DELAY:
                sleep_time = self.RATE_LIMIT_DELAY - elapsed
                logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
                time.sleep(sleep_time)

    def fetch_url(
        self,
        url: str,
        params: Optional[dict] = None,
        timeout: Optional[int] = None,
    ) -> requests.Response:
        """
        Fetch a URL with rate limiting and error handling.

        Args:
            url: URL to fetch.
            params: Query parameters.
            timeout: Request timeout in seconds.

        Returns:
            Response object.

        Raises:
            requests.RequestException: On network errors after retries.
        """
        self._rate_limit()

        try:
            response = self.session.get(
                url,
                params=params,
                timeout=timeout or self.REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            self._last_request_time = time.time()
            return response

        except requests.RequestException as e:
            logger.error(f"Failed to fetch {url}: {e}")
            self._last_request_time = time.time()
            raise

    def log_fetch(
        self,
        fetch_type: str,
        status: str,
        records_fetched: Optional[int] = None,
        error_message: Optional[str] = None,
        duration_seconds: Optional[float] = None,
    ) -> None:
        """
        Log a fetch operation to the database.

        Args:
            fetch_type: Type of fetch (schedule, stats, etc.).
            status: Status (success, failed, partial).
            records_fetched: Number of records fetched.
            error_message: Error message if failed.
            duration_seconds: Duration of fetch.
        """
        try:
            db = get_db()
            with db.session_scope() as session:
                log_entry = DataFetchLog(
                    source=self.source_name,
                    fetch_type=fetch_type,
                    status=status,
                    records_fetched=records_fetched,
                    error_message=error_message,
                    duration_seconds=duration_seconds,
                )
                session.add(log_entry)
            logger.debug(f"Logged fetch: {self.source_name}/{fetch_type} -> {status}")
        except Exception as e:
            logger.warning(f"Failed to log fetch operation: {e}")

    @abstractmethod
    def fetch(self, *args, **kwargs) -> Any:
        """Fetch data from the source. Must be implemented by subclasses."""
        pass

    def close(self) -> None:
        """Close the session."""
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
