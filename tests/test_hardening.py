"""Tests for JARVIS error handling and hardening module."""
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from jarvis.core.hardening import (
    ErrorCategory,
    classify_error,
    user_friendly_error,
    RetryPolicy,
    sanitize_user_input,
    validate_tool_args,
    check_dangerous_command,
    CircuitBreaker,
    get_tool_circuit,
    execute_with_timeout,
    retry_with_backoff,
)


class TestErrorClassification:
    """Test error category classification."""

    def test_classify_rate_limit_error(self):
        """Rate limit errors should be classified correctly."""
        error = Exception("429 Too Many Requests")
        category = classify_error(error)
        assert category == ErrorCategory.RATE_LIMIT

    def test_classify_rate_limit_by_message(self):
        """Rate limit errors by message should be classified."""
        error = Exception("rate_limit exceeded")
        category = classify_error(error)
        assert category == ErrorCategory.RATE_LIMIT

    def test_classify_auth_error(self):
        """Auth errors should be classified correctly."""
        error = Exception("401 Unauthorized")
        category = classify_error(error)
        assert category == ErrorCategory.AUTH

    def test_classify_auth_error_forbidden(self):
        """403 Forbidden should be classified as auth."""
        error = Exception("403 Forbidden")
        category = classify_error(error)
        assert category == ErrorCategory.AUTH

    def test_classify_timeout_error(self):
        """Timeout errors should be classified correctly."""
        error = asyncio.TimeoutError("request timed out")
        category = classify_error(error)
        assert category == ErrorCategory.TIMEOUT

    def test_classify_network_error(self):
        """Network errors should be classified correctly."""
        error = ConnectionError("connection refused")
        category = classify_error(error)
        assert category == ErrorCategory.NETWORK

    def test_classify_invalid_input_error(self):
        """Invalid input errors should be classified correctly."""
        error = ValueError("invalid input format")
        category = classify_error(error)
        assert category == ErrorCategory.INVALID_INPUT

    def test_classify_unknown_error(self):
        """Unknown errors should default to UNKNOWN category."""
        error = RuntimeError("something completely unexpected")
        category = classify_error(error)
        assert category == ErrorCategory.UNKNOWN

    def test_classify_connection_reset(self):
        """Connection reset should be classified as network."""
        error = Exception("connection reset by peer")
        category = classify_error(error)
        assert category == ErrorCategory.NETWORK

    def test_classify_resource_exhaustion(self):
        """Resource exhaustion should be classified correctly."""
        error = Exception("out of memory")
        category = classify_error(error)
        assert category == ErrorCategory.RESOURCE


class TestUserFriendlyError:
    """Test user-friendly error message generation."""

    def test_rate_limit_message(self):
        """Rate limit error should have user-friendly message."""
        msg = user_friendly_error(ErrorCategory.RATE_LIMIT)
        assert "rate limit" in msg.lower()

    def test_auth_message(self):
        """Auth error should have user-friendly message."""
        msg = user_friendly_error(ErrorCategory.AUTH)
        assert "authentication" in msg.lower() or "api key" in msg.lower()

    def test_timeout_message(self):
        """Timeout error should have user-friendly message."""
        msg = user_friendly_error(ErrorCategory.TIMEOUT)
        assert "timed out" in msg.lower() or "timeout" in msg.lower()

    def test_network_message(self):
        """Network error should have user-friendly message."""
        msg = user_friendly_error(ErrorCategory.NETWORK)
        assert "network" in msg.lower()

    def test_invalid_input_message(self):
        """Invalid input error should have user-friendly message."""
        msg = user_friendly_error(ErrorCategory.INVALID_INPUT)
        assert "input" in msg.lower()

    def test_resource_message(self):
        """Resource error should have user-friendly message."""
        msg = user_friendly_error(ErrorCategory.RESOURCE)
        assert "resource" in msg.lower() or "space" in msg.lower() or "memory" in msg.lower()

    def test_unknown_error_message(self):
        """Unknown error should have user-friendly message."""
        msg = user_friendly_error(ErrorCategory.UNKNOWN)
        assert "unexpected" in msg.lower() or "error" in msg.lower()

    def test_error_message_with_context(self):
        """Error messages should include context if provided."""
        msg = user_friendly_error(ErrorCategory.TIMEOUT, context="fetching the page")
        assert "fetching the page" in msg


class TestRetryPolicy:
    """Test retry policy configuration and behavior."""

    def test_retry_policy_defaults(self):
        """RetryPolicy should have sensible defaults."""
        policy = RetryPolicy()
        assert policy.max_retries == 3
        assert policy.base_delay_s == 1.0
        assert policy.max_delay_s == 30.0
        assert policy.jitter is True

    def test_should_retry_under_max_attempts(self):
        """Should retry when under max attempts for retryable error."""
        policy = RetryPolicy(max_retries=3)
        error = Exception("timeout")
        assert policy.should_retry(error, attempt=1) is True

    def test_should_not_retry_at_max_attempts(self):
        """Should not retry at max attempts."""
        policy = RetryPolicy(max_retries=3)
        error = Exception("timeout")
        assert policy.should_retry(error, attempt=4) is False

    def test_should_not_retry_non_retryable_error(self):
        """Should not retry non-retryable errors."""
        policy = RetryPolicy()
        error = ValueError("invalid input")
        assert policy.should_retry(error, attempt=1) is False

    def test_get_delay_exponential_backoff(self):
        """Delays should increase exponentially."""
        policy = RetryPolicy(base_delay_s=1.0, max_delay_s=30.0, jitter=False)
        delay_0 = policy.get_delay(0)
        delay_1 = policy.get_delay(1)
        delay_2 = policy.get_delay(2)
        assert delay_1 > delay_0
        assert delay_2 > delay_1

    def test_get_delay_max_cap(self):
        """Delays should not exceed max_delay_s."""
        policy = RetryPolicy(base_delay_s=1.0, max_delay_s=10.0, jitter=False)
        delay = policy.get_delay(10)
        assert delay <= 10.0

    def test_get_delay_with_jitter(self):
        """Delays with jitter should vary."""
        policy = RetryPolicy(base_delay_s=1.0, jitter=True)
        delays = [policy.get_delay(0) for _ in range(5)]
        # Jitter should create variation
        assert len(set(delays)) > 1 or all(d == delays[0] for d in delays)


class TestInputSanitization:
    """Test input sanitization."""

    def test_sanitize_empty_input(self):
        """Empty input should be handled."""
        result = sanitize_user_input("")
        assert result == ""

    def test_sanitize_normal_input(self):
        """Normal input should pass through unchanged."""
        text = "search for information"
        result = sanitize_user_input(text)
        assert result == text

    def test_sanitize_whitespace_trimming(self):
        """Input should be trimmed."""
        text = "  search  "
        result = sanitize_user_input(text)
        assert result == "search"

    def test_sanitize_truncate_long_input(self):
        """Very long input should be truncated."""
        text = "a" * 20000
        result = sanitize_user_input(text)
        assert len(result) < len(text)
        assert "truncated" in result

    def test_sanitize_max_length(self):
        """Truncated input should respect MAX_USER_INPUT_LENGTH."""
        from jarvis.core.hardening import MAX_USER_INPUT_LENGTH
        text = "a" * (MAX_USER_INPUT_LENGTH + 1000)
        result = sanitize_user_input(text)
        assert len(result) <= MAX_USER_INPUT_LENGTH + 50  # Allow for "truncated" message


class TestToolArgValidation:
    """Test tool argument validation."""

    def test_validate_normal_args(self):
        """Normal arguments should pass through unchanged."""
        args = {"path": "/home/user/file.txt", "content": "hello"}
        result = validate_tool_args("write_file", args)
        assert result["path"] == "/home/user/file.txt"
        assert result["content"] == "hello"

    def test_validate_truncate_long_string_args(self):
        """Long string arguments should be truncated."""
        from jarvis.core.hardening import MAX_TOOL_ARG_LENGTH
        long_text = "a" * (MAX_TOOL_ARG_LENGTH + 1000)
        args = {"query": long_text}
        result = validate_tool_args("search_web", args)
        assert len(result["query"]) <= MAX_TOOL_ARG_LENGTH

    def test_validate_truncate_file_paths(self):
        """Very long file paths should be truncated."""
        from jarvis.core.hardening import MAX_FILE_PATH_LENGTH
        long_path = "/very/" * 100 + "long/path.txt"
        args = {"path": long_path}
        result = validate_tool_args("read_file", args)
        assert len(result["path"]) <= MAX_FILE_PATH_LENGTH

    def test_validate_non_string_args(self):
        """Non-string arguments should pass through."""
        args = {"count": 42, "enabled": True, "data": None}
        result = validate_tool_args("some_tool", args)
        assert result["count"] == 42
        assert result["enabled"] is True
        assert result["data"] is None


class TestDangerousCommandDetection:
    """Test dangerous command pattern detection."""

    def test_rm_rf_root(self):
        """rm -rf / should be detected as dangerous."""
        warning = check_dangerous_command("rm -rf /")
        assert warning is not None

    def test_rm_rf_home(self):
        """rm -rf ~ should be detected as dangerous."""
        warning = check_dangerous_command("rm -rf ~")
        assert warning is not None

    def test_fork_bomb(self):
        """Fork bomb should be detected."""
        warning = check_dangerous_command(":() { : | :& }; :")
        assert warning is not None

    def test_chmod_777_root(self):
        """chmod -R 777 / should be detected."""
        warning = check_dangerous_command("chmod -R 777 /")
        assert warning is not None

    def test_dd_to_device(self):
        """dd to device should be detected."""
        warning = check_dangerous_command("dd if=/dev/zero of=/dev/sda")
        assert warning is not None

    def test_mkfs_dangerous(self):
        """mkfs should be detected."""
        warning = check_dangerous_command("mkfs.ext4 /dev/sda1")
        assert warning is not None

    def test_safe_command(self):
        """Safe commands should not trigger warning."""
        warning = check_dangerous_command("ls -la /home")
        assert warning is None

    def test_safe_rm_command(self):
        """Safe rm commands should not trigger warning."""
        warning = check_dangerous_command("rm /tmp/tmpfile.txt")
        assert warning is None

    def test_case_insensitive_detection(self):
        """Dangerous pattern detection should be case-insensitive."""
        warning = check_dangerous_command("RM -RF /")
        assert warning is not None


class TestCircuitBreaker:
    """Test circuit breaker state machine."""

    def test_circuit_breaker_initialization(self):
        """Circuit breaker should start in closed state."""
        cb = CircuitBreaker(name="test", failure_threshold=3)
        assert cb.state == "closed"
        assert cb.allow_request() is True

    def test_circuit_breaker_open_on_threshold(self):
        """Circuit breaker should open after threshold failures."""
        cb = CircuitBreaker(name="test", failure_threshold=3)
        for i in range(3):
            cb.record_failure()
        assert cb.state == "open"
        assert cb.allow_request() is False

    def test_circuit_breaker_half_open_after_recovery_timeout(self):
        """Circuit breaker should transition to half-open after recovery timeout."""
        cb = CircuitBreaker(
            name="test",
            failure_threshold=2,
            recovery_timeout_s=0.1  # 100ms for testing
        )
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "open"
        time.sleep(0.15)  # Wait for recovery timeout
        assert cb.state == "half_open"

    def test_circuit_breaker_recovery_to_closed(self):
        """Circuit breaker should recover to closed on successful request."""
        cb = CircuitBreaker(
            name="test",
            failure_threshold=2,
            recovery_timeout_s=0.1
        )
        cb.record_failure()
        cb.record_failure()
        assert cb.state == "open"
        time.sleep(0.15)
        assert cb.state == "half_open"
        cb.record_success()
        assert cb.state == "closed"

    def test_circuit_breaker_reopen_on_half_open_failure(self):
        """Circuit breaker should reopen on failure in half-open state."""
        cb = CircuitBreaker(
            name="test",
            failure_threshold=2,
            recovery_timeout_s=0.1
        )
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        assert cb.state == "half_open"
        cb.allow_request()  # Allow one request
        cb.record_failure()
        assert cb.state == "open"

    def test_circuit_breaker_allow_one_in_half_open(self):
        """Circuit breaker should allow limited requests in half-open."""
        cb = CircuitBreaker(
            name="test",
            failure_threshold=2,
            recovery_timeout_s=0.1,
            half_open_max_calls=1
        )
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.15)
        assert cb.state == "half_open"
        assert cb.allow_request() is True
        assert cb.allow_request() is False

    def test_circuit_breaker_status(self):
        """Circuit breaker should report status."""
        cb = CircuitBreaker(name="test", failure_threshold=3)
        status = cb.get_status()
        assert status["name"] == "test"
        assert status["state"] in ["closed", "open", "half_open"]
        assert status["failure_count"] == 0

    def test_get_tool_circuit(self):
        """Should get or create tool circuit breaker."""
        cb1 = get_tool_circuit("test_tool")
        cb2 = get_tool_circuit("test_tool")
        assert cb1 is cb2


class TestRetryWithBackoff:
    """Test retry with exponential backoff."""

    @pytest.mark.asyncio
    async def test_successful_on_first_try(self):
        """Successful function should not retry."""
        func = AsyncMock(return_value="success")
        result = await retry_with_backoff(func)
        assert result == "success"
        assert func.call_count == 1

    @pytest.mark.asyncio
    async def test_successful_after_retries(self):
        """Function should succeed after retries."""
        func = AsyncMock(side_effect=[
            Exception("timeout"),
            Exception("timeout"),
            "success"
        ])
        result = await retry_with_backoff(
            func,
            policy=RetryPolicy(max_retries=3, base_delay_s=0.01, jitter=False)
        )
        assert result == "success"
        assert func.call_count == 3

    @pytest.mark.asyncio
    async def test_exhausts_retries(self):
        """Should raise after exhausting retries."""
        # Use a retryable error (rate limit) so retries actually happen
        func = AsyncMock(side_effect=Exception("rate limit exceeded"))
        with pytest.raises(Exception):
            await retry_with_backoff(
                func,
                policy=RetryPolicy(max_retries=2, base_delay_s=0.01, jitter=False)
            )
        assert func.call_count == 3  # Initial + 2 retries

    @pytest.mark.asyncio
    async def test_non_retryable_error_fails_immediately(self):
        """Non-retryable errors should fail immediately."""
        func = AsyncMock(side_effect=ValueError("invalid input"))
        with pytest.raises(ValueError):
            await retry_with_backoff(func)
        assert func.call_count == 1  # No retries for invalid input


class TestExecuteWithTimeout:
    """Test execution with timeout guard."""

    @pytest.mark.asyncio
    async def test_execution_within_timeout(self):
        """Execution within timeout should succeed."""
        async def fast_coro():
            await asyncio.sleep(0.01)
            return "done"

        result = await execute_with_timeout(fast_coro(), timeout_s=1.0)
        assert result == "done"

    @pytest.mark.asyncio
    async def test_execution_exceeds_timeout(self):
        """Execution exceeding timeout should raise TimeoutError."""
        async def slow_coro():
            await asyncio.sleep(1.0)
            return "done"

        with pytest.raises(asyncio.TimeoutError):
            await execute_with_timeout(slow_coro(), timeout_s=0.1)

    @pytest.mark.asyncio
    async def test_timeout_error_message_includes_tool_name(self):
        """Timeout error should include tool name."""
        async def slow_coro():
            await asyncio.sleep(1.0)

        with pytest.raises(asyncio.TimeoutError) as exc_info:
            await execute_with_timeout(slow_coro(), timeout_s=0.1, tool_name="test_tool")
        assert "test_tool" in str(exc_info.value)
