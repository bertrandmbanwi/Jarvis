"""Production-grade error handling, retry logic, timeouts, input sanitization, and circuit breaking."""
import asyncio
import logging
import random
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger("jarvis.hardening")


class ErrorCategory(str, Enum):
    """Categorized error types for structured handling."""
    RATE_LIMIT = "rate_limit"
    AUTH = "auth"
    TIMEOUT = "timeout"
    NETWORK = "network"
    INVALID_INPUT = "invalid_input"
    TOOL_FAILURE = "tool_failure"
    API_ERROR = "api_error"
    RESOURCE = "resource"
    UNKNOWN = "unknown"


_ERROR_PATTERNS = [
    (ErrorCategory.RATE_LIMIT, [
        r"rate.?limit", r"429", r"too many requests",
        r"overloaded", r"capacity", r"throttl",
    ]),
    (ErrorCategory.AUTH, [
        r"401", r"403", r"unauthorized", r"forbidden",
        r"invalid.?api.?key", r"authentication", r"permission.?denied",
    ]),
    (ErrorCategory.TIMEOUT, [
        r"timeout", r"timed?.?out", r"deadline.?exceeded",
        r"read timeout", r"connect timeout",
    ]),
    (ErrorCategory.NETWORK, [
        r"connection.?refused", r"connection.?reset",
        r"dns.?resolution", r"unreachable", r"network",
        r"connect.?error", r"ssl.?error",
    ]),
    (ErrorCategory.INVALID_INPUT, [
        r"invalid.?input", r"validation.?error",
        r"missing.?required", r"bad.?request", r"400",
    ]),
    (ErrorCategory.RESOURCE, [
        r"out.?of.?memory", r"disk.?full", r"no.?space",
        r"resource.?exhausted", r"quota.?exceeded",
    ]),
]


def classify_error(error: Exception) -> ErrorCategory:
    """Classify an exception into a structured error category."""
    error_str = str(error).lower()
    error_type = type(error).__name__.lower()
    combined = f"{error_type}: {error_str}"

    for category, patterns in _ERROR_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, combined):
                return category

    # Check by exception type
    if isinstance(error, asyncio.TimeoutError):
        return ErrorCategory.TIMEOUT
    if isinstance(error, ConnectionError):
        return ErrorCategory.NETWORK
    if isinstance(error, ValueError):
        return ErrorCategory.INVALID_INPUT

    return ErrorCategory.UNKNOWN


def user_friendly_error(category: ErrorCategory, context: str = "") -> str:
    """Generate user-friendly error message for a category."""
    ctx = f" while {context}" if context else ""

    messages = {
        ErrorCategory.RATE_LIMIT: (
            f"I hit an API rate limit{ctx}. I'll wait a moment and try again."
        ),
        ErrorCategory.AUTH: (
            f"I encountered an authentication issue{ctx}. "
            "The API key may need to be refreshed."
        ),
        ErrorCategory.TIMEOUT: (
            f"The request timed out{ctx}. "
            "The service might be slow right now. I can try again if you'd like."
        ),
        ErrorCategory.NETWORK: (
            f"I'm having trouble reaching the network{ctx}. "
            "Please check the internet connection."
        ),
        ErrorCategory.INVALID_INPUT: (
            f"There was an issue with the input{ctx}. "
            "Could you rephrase or double-check the details?"
        ),
        ErrorCategory.TOOL_FAILURE: (
            f"A tool encountered an error{ctx}. "
            "I'll try an alternative approach."
        ),
        ErrorCategory.API_ERROR: (
            f"The API returned an error{ctx}. "
            "This may be a temporary issue on the provider's side."
        ),
        ErrorCategory.RESOURCE: (
            f"A resource limit was reached{ctx}. "
            "The system may need more disk space or memory."
        ),
        ErrorCategory.UNKNOWN: (
            f"Something unexpected went wrong{ctx}. "
            "I've logged the details for troubleshooting."
        ),
    }
    return messages.get(category, messages[ErrorCategory.UNKNOWN])


@dataclass
class RetryPolicy:
    """Configurable retry policy with exponential backoff and jitter."""
    max_retries: int = 3
    base_delay_s: float = 1.0
    max_delay_s: float = 30.0
    jitter: bool = True
    retryable_categories: set[ErrorCategory] = field(default_factory=lambda: {
        ErrorCategory.RATE_LIMIT,
        ErrorCategory.TIMEOUT,
        ErrorCategory.NETWORK,
        ErrorCategory.API_ERROR,
    })

    def should_retry(self, error: Exception, attempt: int) -> bool:
        """Determine if a failed request should be retried."""
        if attempt >= self.max_retries:
            return False
        category = classify_error(error)
        return category in self.retryable_categories

    def get_delay(self, attempt: int) -> float:
        """Calculate the delay before the next retry attempt."""
        delay = min(self.base_delay_s * (2 ** attempt), self.max_delay_s)
        if self.jitter:
            delay *= (0.5 + random.random())  # 50%-150% of calculated delay
        return delay


API_RETRY_POLICY = RetryPolicy(max_retries=3, base_delay_s=1.0, max_delay_s=30.0)
TOOL_RETRY_POLICY = RetryPolicy(
    max_retries=1, base_delay_s=0.5, max_delay_s=5.0,
    retryable_categories={ErrorCategory.TIMEOUT, ErrorCategory.NETWORK},
)


async def retry_with_backoff(
    func: Callable,
    *args,
    policy: RetryPolicy = API_RETRY_POLICY,
    context: str = "",
    **kwargs,
) -> Any:
    """Execute async function with retry and exponential backoff."""
    last_error = None

    for attempt in range(policy.max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_error = e
            category = classify_error(e)

            if not policy.should_retry(e, attempt + 1):
                logger.warning(
                    "Non-retryable error (%s) on attempt %d/%d%s: %s",
                    category.value, attempt + 1, policy.max_retries + 1,
                    f" [{context}]" if context else "", str(e)[:200],
                )
                raise

            delay = policy.get_delay(attempt)
            logger.info(
                "Retryable error (%s) on attempt %d/%d%s. "
                "Waiting %.1fs before retry. Error: %s",
                category.value, attempt + 1, policy.max_retries + 1,
                f" [{context}]" if context else "", delay, str(e)[:200],
            )
            await asyncio.sleep(delay)

    # Should not reach here, but just in case
    raise last_error


TOOL_TIMEOUTS: dict[str, float] = {
    "get_system_info": 10.0,
    "get_battery_status": 5.0,
    "get_clipboard": 5.0,
    "set_clipboard": 5.0,
    "set_volume": 5.0,
    "set_brightness": 5.0,
    "get_running_applications": 10.0,
    "get_frontmost_application": 5.0,
    "get_unread_count": 15.0,
    "get_calendar_list": 15.0,
    "send_notification": 5.0,
    "read_file": 15.0,
    "write_file": 15.0,
    "list_directory": 10.0,
    "search_files": 30.0,
    "get_upcoming_events": 20.0,
    "create_calendar_event": 20.0,
    "search_calendar_events": 25.0,
    "get_recent_emails": 20.0,
    "send_email": 20.0,
    "search_emails": 25.0,
    "read_email": 20.0,
    "search_web": 30.0,
    "search_news": 30.0,
    "search_and_read": 45.0,
    "fetch_page_text": 30.0,
    "fetch_page_links": 30.0,
    "run_command": 60.0,
    "run_claude_code": 120.0,
    "run_terminal_command_smart": 60.0,
    "scaffold_project": 90.0,
    "browse_web": 60.0,
    "browser_navigate": 30.0,
    "browser_screenshot": 20.0,
    "chrome_navigate": 20.0,
    "chrome_click": 15.0,
    "chrome_type": 15.0,
    "chrome_read_page": 20.0,
    "chrome_find_elements": 15.0,
    "chrome_screenshot": 15.0,
    "chrome_execute_js": 20.0,
    "chrome_fill_form": 20.0,
    "capture_screen": 15.0,
    "read_screen_text": 20.0,
}

DEFAULT_TOOL_TIMEOUT = 30.0  # seconds


def get_tool_timeout(tool_name: str) -> float:
    """Get the timeout for a specific tool."""
    return TOOL_TIMEOUTS.get(tool_name, DEFAULT_TOOL_TIMEOUT)


async def execute_with_timeout(
    coro,
    timeout_s: float,
    tool_name: str = "",
) -> Any:
    """Execute coroutine with timeout guard."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout_s)
    except asyncio.TimeoutError:
        logger.warning(
            "Tool '%s' timed out after %.1fs",
            tool_name or "unknown", timeout_s,
        )
        raise asyncio.TimeoutError(
            f"Tool '{tool_name}' timed out after {timeout_s:.0f}s. "
            f"The operation took too long to complete."
        )


MAX_USER_INPUT_LENGTH = 10000
MAX_TOOL_ARG_LENGTH = 5000
MAX_FILE_PATH_LENGTH = 500

_DANGEROUS_SHELL_PATTERNS = [
    r"rm\s+(-rf?|--force)\s+[/~]",  # rm -rf /
    r">\s*/dev/sd[a-z]",             # Writing to disk devices
    r"mkfs\.",                        # Formatting filesystems
    r"dd\s+.*of=/dev/",             # dd to devices
    r":(){ :\|:& };:",              # Fork bomb
    r"chmod\s+-R\s+777\s+/",       # Recursive 777 on root
]


def sanitize_user_input(text: str) -> str:
    """Sanitize user input by trimming whitespace and capping length."""
    if not text:
        return ""

    text = text.strip()

    if len(text) > MAX_USER_INPUT_LENGTH:
        logger.warning(
            "User input truncated from %d to %d characters.",
            len(text), MAX_USER_INPUT_LENGTH,
        )
        text = text[:MAX_USER_INPUT_LENGTH] + "... (input truncated)"

    return text


def validate_tool_args(tool_name: str, args: dict) -> dict:
    """Validate and sanitize tool arguments."""
    cleaned = {}
    for key, value in args.items():
        if isinstance(value, str):
            # Cap string argument length
            if len(value) > MAX_TOOL_ARG_LENGTH:
                logger.warning(
                    "Tool '%s' arg '%s' truncated from %d to %d chars.",
                    tool_name, key, len(value), MAX_TOOL_ARG_LENGTH,
                )
                value = value[:MAX_TOOL_ARG_LENGTH]

            # Validate file paths
            if key in ("path", "file_path", "directory", "source", "destination"):
                if len(value) > MAX_FILE_PATH_LENGTH:
                    logger.warning(
                        "Tool '%s' file path too long (%d chars).",
                        tool_name, len(value),
                    )
                    value = value[:MAX_FILE_PATH_LENGTH]

        cleaned[key] = value

    return cleaned


def check_dangerous_command(command: str) -> Optional[str]:
    """Check if command contains dangerous patterns (warns but doesn't block)."""
    for pattern in _DANGEROUS_SHELL_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return (
                f"Warning: this command matches a dangerous pattern ({pattern}). "
                f"Proceeding with caution."
            )
    return None


@dataclass
class CircuitBreaker:
    """Prevents cascading failures with CLOSED/OPEN/HALF_OPEN states."""
    name: str
    failure_threshold: int = 5
    recovery_timeout_s: float = 60.0
    half_open_max_calls: int = 1

    _failure_count: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0.0, init=False)
    _state: str = field(default="closed", init=False)
    _half_open_calls: int = field(default=0, init=False)

    @property
    def state(self) -> str:
        """Get current state, auto-transitioning from open to half-open."""
        if self._state == "open":
            elapsed = time.time() - self._last_failure_time
            if elapsed >= self.recovery_timeout_s:
                self._state = "half_open"
                self._half_open_calls = 0
                logger.info(
                    "Circuit breaker '%s': open -> half_open (recovery window reached)",
                    self.name,
                )
        return self._state

    def allow_request(self) -> bool:
        """Check if a request should be allowed through."""
        state = self.state  # Triggers auto-transition check
        if state == "closed":
            return True
        if state == "half_open":
            if self._half_open_calls < self.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False
        return False  # open

    def record_success(self):
        """Record a successful request."""
        if self._state == "half_open":
            self._state = "closed"
            self._failure_count = 0
            logger.info(
                "Circuit breaker '%s': half_open -> closed (recovery confirmed)",
                self.name,
            )
        elif self._state == "closed":
            # Reset failure count on success
            self._failure_count = max(0, self._failure_count - 1)

    def record_failure(self):
        """Record a failed request."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == "half_open":
            self._state = "open"
            logger.warning(
                "Circuit breaker '%s': half_open -> open (recovery failed)",
                self.name,
            )
        elif self._failure_count >= self.failure_threshold:
            self._state = "open"
            logger.warning(
                "Circuit breaker '%s': closed -> open "
                "(%d failures in succession, threshold: %d)",
                self.name, self._failure_count, self.failure_threshold,
            )

    def get_status(self) -> dict:
        return {
            "name": self.name,
            "state": self.state,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout_s": self.recovery_timeout_s,
        }


claude_circuit = CircuitBreaker(name="claude_api", failure_threshold=5, recovery_timeout_s=60.0)
ollama_circuit = CircuitBreaker(name="ollama", failure_threshold=3, recovery_timeout_s=30.0)

tool_circuits: dict[str, CircuitBreaker] = {}


def get_tool_circuit(tool_name: str) -> CircuitBreaker:
    """Get or create a circuit breaker for a specific tool."""
    if tool_name not in tool_circuits:
        tool_circuits[tool_name] = CircuitBreaker(
            name=f"tool:{tool_name}",
            failure_threshold=3,
            recovery_timeout_s=120.0,
        )
    return tool_circuits[tool_name]


def get_health_report() -> dict:
    """Get a comprehensive health report of all hardening subsystems."""
    circuit_statuses = {
        "claude_api": claude_circuit.get_status(),
        "ollama": ollama_circuit.get_status(),
    }

    # Include tool circuits that have had failures
    for name, cb in tool_circuits.items():
        if cb._failure_count > 0 or cb._state != "closed":
            circuit_statuses[name] = cb.get_status()

    return {
        "circuit_breakers": circuit_statuses,
        "tool_timeouts": {
            "default_timeout_s": DEFAULT_TOOL_TIMEOUT,
            "custom_timeout_count": len(TOOL_TIMEOUTS),
        },
        "input_limits": {
            "max_user_input": MAX_USER_INPUT_LENGTH,
            "max_tool_arg": MAX_TOOL_ARG_LENGTH,
            "max_file_path": MAX_FILE_PATH_LENGTH,
        },
    }
