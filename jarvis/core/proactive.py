"""Background engine that monitors context and generates proactive suggestions."""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger("jarvis.core.proactive")


class SuggestionCategory(str, Enum):
    """Categories of proactive suggestions."""
    CALENDAR = "calendar"
    EMAIL = "email"
    GREETING = "greeting"
    REMINDER = "reminder"


@dataclass
class Suggestion:
    """A single proactive suggestion."""
    category: SuggestionCategory
    message: str
    priority: int = 0  # Higher = more important
    timestamp: float = field(default_factory=time.time)
    spoken: bool = False  # Whether this should be spoken aloud


DEFAULT_INTERVALS = {
    SuggestionCategory.CALENDAR: 300,
    SuggestionCategory.EMAIL: 600,
    SuggestionCategory.GREETING: 3600,
    SuggestionCategory.REMINDER: 900,
}

COOLDOWN_PERIODS = {
    SuggestionCategory.CALENDAR: 600,
    SuggestionCategory.EMAIL: 1800,
    SuggestionCategory.GREETING: 14400,
    SuggestionCategory.REMINDER: 1800,
}

MEETING_ALERT_MINUTES = [15, 5]


class ProactiveEngine:
    """Background engine that monitors context and generates suggestions."""

    def __init__(self):
        self._enabled = True
        self._running = False
        self._task: Optional[asyncio.Task] = None

        self._category_enabled: dict[SuggestionCategory, bool] = {cat: True for cat in SuggestionCategory}
        self._intervals: dict[SuggestionCategory, int] = dict(DEFAULT_INTERVALS)
        self._last_check: dict[SuggestionCategory, float] = {cat: 0.0 for cat in SuggestionCategory}
        self._last_suggestion: dict[SuggestionCategory, float] = {cat: 0.0 for cat in SuggestionCategory}
        self._alerted_events: set[str] = set()
        self._greeting_sent_today: str = ""
        self._on_suggestion: Optional[Callable] = None
        self._conversation_active = False
        self._last_interaction: float = 0.0

    def start(self):
        """Start the heartbeat loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._heartbeat_loop())
        logger.info("Proactive engine started (heartbeat interval: base 60s).")

    def stop(self):
        """Stop the heartbeat loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("Proactive engine stopped.")

    def mark_interaction(self):
        """Mark user interaction to suppress suggestions during active conversation."""
        self._last_interaction = time.time()
        self._conversation_active = True

    def mark_idle(self):
        """Mark that the conversation has gone idle."""
        self._conversation_active = False

    def set_category_enabled(self, category: SuggestionCategory, enabled: bool):
        """Enable or disable a suggestion category."""
        self._category_enabled[category] = enabled
        logger.info("Proactive category %s: %s", category.value, "enabled" if enabled else "disabled")

    def set_enabled(self, enabled: bool):
        """Enable or disable the entire proactive engine."""
        self._enabled = enabled
        logger.info("Proactive engine: %s", "enabled" if enabled else "disabled")

    def get_status(self) -> dict:
        """Get the current status of the proactive engine."""
        return {
            "enabled": self._enabled,
            "running": self._running,
            "categories": {
                cat.value: {
                    "enabled": self._category_enabled[cat],
                    "interval_s": self._intervals[cat],
                    "last_check": self._last_check[cat],
                    "last_suggestion": self._last_suggestion[cat],
                }
                for cat in SuggestionCategory
            },
            "conversation_active": self._conversation_active,
            "seconds_since_interaction": round(time.time() - self._last_interaction, 1) if self._last_interaction else 0,
        }

    async def _heartbeat_loop(self):
        """Main background loop running checks every 60 seconds."""
        await asyncio.sleep(30)

        while self._running:
            try:
                if self._enabled and not self._conversation_active:
                    await self._run_checks()
                elif self._conversation_active:
                    if time.time() - self._last_interaction > 300:
                        self._conversation_active = False
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("Proactive heartbeat error: %s", e)

            await asyncio.sleep(60)

    async def _run_checks(self):
        """Run all due context checks."""

        now = time.time()

        for category in SuggestionCategory:
            if not self._category_enabled[category]:
                continue

            interval = self._intervals[category]
            if now - self._last_check[category] < interval:
                continue

            # Check cooldown
            cooldown = COOLDOWN_PERIODS[category]
            if now - self._last_suggestion[category] < cooldown:
                continue

            self._last_check[category] = now
            try:
                if category == SuggestionCategory.CALENDAR:
                    await self._check_calendar()
                elif category == SuggestionCategory.EMAIL:
                    await self._check_email()
                elif category == SuggestionCategory.GREETING:
                    await self._check_greeting()
            except Exception as e:
                logger.debug("Proactive check %s failed: %s", category.value, e)

    async def _check_calendar(self):
        """Check for upcoming calendar events and alert if one is soon."""
        try:
            from jarvis.tools.calendar_email import get_upcoming_events
            events_text = await get_upcoming_events(days=1)
        except Exception as e:
            logger.debug("Calendar check failed: %s", e)
            return

        if "No events found" in events_text:
            return

        # Parse events to find ones starting soon
        now = time.time()
        lines = [l.strip() for l in events_text.strip().split("\n") if l.strip()]

        for line in lines:
            # Each line format: "Title | DateTime - DateTime | Calendar: Name"
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 2:
                continue

            title = parts[0]
            time_str = parts[1] if len(parts) > 1 else ""

            if "All Day" in time_str:
                continue

            event_key = f"{title}_{time_str}"
            if event_key in self._alerted_events:
                continue

            try:
                from datetime import datetime
                start_str = time_str.split(" - ")[0].strip()
                for fmt in [
                    "%A, %B %d, %Y at %I:%M:%S %p",
                    "%m/%d/%Y %I:%M:%S %p",
                    "%Y-%m-%d %H:%M:%S",
                ]:
                    try:
                        event_time = datetime.strptime(start_str, fmt)
                        minutes_until = (event_time.timestamp() - time.time()) / 60

                        for alert_mins in MEETING_ALERT_MINUTES:
                            if 0 < minutes_until <= alert_mins + 1:
                                self._alerted_events.add(event_key)
                                location_info = ""
                                if len(parts) > 2:
                                    for p in parts[2:]:
                                        if "Location:" in p:
                                            location_info = f" at {p.replace('Location:', '').strip()}"

                                msg = (
                                    f"Heads up, sir. You have '{title}' starting "
                                    f"in about {int(minutes_until)} minutes{location_info}."
                                )
                                await self._deliver(Suggestion(
                                    category=SuggestionCategory.CALENDAR,
                                    message=msg,
                                    priority=2,
                                    spoken=True,
                                ))
                                return
                        break  # Successfully parsed, no need to try other formats
                    except ValueError:
                        continue
            except Exception:
                # If we can't parse the time, skip this event
                continue

    async def _check_email(self):
        """Check for new unread emails and notify if count is noteworthy."""
        try:
            from jarvis.tools.calendar_email import get_unread_count
            unread_text = await asyncio.wait_for(get_unread_count(), timeout=8.0)
        except asyncio.TimeoutError:
            logger.debug("Email check timed out (Mail app not responding).")
            return
        except Exception as e:
            logger.debug("Email check failed: %s", e)
            return

        if "No unread" in unread_text or "inbox zero" in unread_text.lower():
            return

        # Extract total unread count
        try:
            # Format: "Unread emails (X total):\nAccount: N unread\n..."
            if "total" in unread_text:
                count_str = unread_text.split("(")[1].split("total")[0].strip()
                total_unread = int(count_str)
            else:
                return

            # Only notify if there are a meaningful number of unread emails
            # and we haven't recently notified about email
            if total_unread >= 3:
                msg = f"Sir, you have {total_unread} unread emails waiting."
                await self._deliver(Suggestion(
                    category=SuggestionCategory.EMAIL,
                    message=msg,
                    priority=1,
                    spoken=False,  # Email notifications are less urgent, text only
                ))
        except (ValueError, IndexError):
            pass

    async def _check_greeting(self):
        """Send time-appropriate greetings."""
        from datetime import datetime
        now = datetime.now()
        hour = now.hour
        today = now.strftime("%Y-%m-%d")

        # Reset greeting tracker at midnight
        if self._greeting_sent_today and not self._greeting_sent_today.startswith(today):
            self._greeting_sent_today = ""

        if 6 <= hour < 12 and f"{today}_morning" != self._greeting_sent_today:
            self._greeting_sent_today = f"{today}_morning"
            # Build a morning briefing
            briefing = await self._build_morning_briefing()
            msg = f"Good morning, sir. {briefing}"
            await self._deliver(Suggestion(
                category=SuggestionCategory.GREETING,
                message=msg,
                priority=0,
                spoken=True,
            ))
        elif 12 <= hour < 17 and f"{today}_afternoon" != self._greeting_sent_today:
            # Only send afternoon greeting if morning was already sent
            if f"{today}_morning" == self._greeting_sent_today:
                return  # Already greeted today
            self._greeting_sent_today = f"{today}_afternoon"
            msg = "Good afternoon, sir. Let me know if you need anything."
            await self._deliver(Suggestion(
                category=SuggestionCategory.GREETING,
                message=msg,
                priority=0,
                spoken=True,
            ))

    async def _build_morning_briefing(self) -> str:
        """Build a concise morning briefing from calendar and email."""
        parts = []

        # Check calendar
        try:
            from jarvis.tools.calendar_email import get_upcoming_events
            events = await get_upcoming_events(days=1)
            if "No events found" not in events:
                event_lines = [l for l in events.strip().split("\n") if l.strip()]
                count = len(event_lines)
                if count == 1:
                    parts.append("You have 1 event on your calendar today.")
                else:
                    parts.append(f"You have {count} events on your calendar today.")
        except Exception:
            pass

        # Check email (with timeout guard; AppleScript Mail can hang)
        try:
            from jarvis.tools.calendar_email import get_unread_count
            unread = await asyncio.wait_for(get_unread_count(), timeout=8.0)
            if "No unread" not in unread and "inbox zero" not in unread.lower():
                try:
                    count_str = unread.split("(")[1].split("total")[0].strip()
                    total = int(count_str)
                    if total > 0:
                        parts.append(f"You have {total} unread emails.")
                except (ValueError, IndexError):
                    pass
        except asyncio.TimeoutError:
            logger.debug("Email check timed out during morning briefing.")
        except Exception:
            pass

        if not parts:
            return "Your schedule looks clear today."

        return " ".join(parts)

    async def _deliver(self, suggestion: Suggestion):
        """Deliver a suggestion via registered callback."""

        self._last_suggestion[suggestion.category] = time.time()

        logger.info(
            "Proactive suggestion [%s]: %s",
            suggestion.category.value,
            suggestion.message[:80],
        )

        if self._on_suggestion:
            try:
                await self._on_suggestion(suggestion)
            except Exception as e:
                logger.debug("Suggestion delivery failed: %s", e)

    def cleanup_old_alerts(self):
        """Remove stale event alert keys."""
        if len(self._alerted_events) > 200:
            self._alerted_events.clear()
