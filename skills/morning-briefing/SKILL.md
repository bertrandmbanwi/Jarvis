---
name: morning-briefing
description: Give the user a short spoken briefing for the day - weather, calendar, unread email, and anything that needs attention. Use when asked for a morning briefing, a daily rundown, or "what's my day look like".
---

# Morning briefing

Build a briefing the user can listen to in under a minute.

## Gather (run these in parallel)
1. `get_weather` for the user's saved location.
2. `get_upcoming_events` with `days=1` for today's calendar.
3. `get_unread_count` for email.
4. `get_battery_status` only if the Mac is on battery below 20%.

If a tool fails or isn't connected, skip that section silently rather than apologising.

## Compose
- Open with a greeting that fits the time of day.
- Weather in one sentence: conditions, high and low, and whether to bring a jacket or umbrella.
- Calendar: the number of events, then the first one with its time. Call out back-to-back meetings or early starts. If the day is empty, say so.
- Email: the unread count only. Don't read messages aloud unless asked.
- Finish with one practical suggestion, such as leaving early for the first meeting because of rain.

## Style
- Spoken, not written: no lists, headings or markdown.
- Round numbers ("about 18 degrees"), 12-hour times ("half past nine").
- Keep it under 90 words.
