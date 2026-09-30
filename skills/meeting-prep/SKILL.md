---
name: meeting-prep
description: Prepare the user for an upcoming meeting - who is attending, what it is about, and related notes or emails. Use when asked to prep for a meeting, "what's my next meeting about", or "brief me before my call".
---

# Meeting prep

## Find the meeting
1. `get_upcoming_events` (`days=1`, or `days=7` if the user names a later meeting). Pick the next meeting, or the one the user named.
2. If nothing matches, say so and stop.

## Gather context
3. `search_emails` for the meeting title and for each attendee's name, limited to recent results.
4. `search_notes` for the title and the main topic.
5. `search_calendar_events` for earlier meetings with the same title, to spot a recurring series.

Only use what the tools return. Don't guess at attendees' roles or at an agenda.

## Brief the user
- Start with the time and how long until it begins ("Your 2pm with Sam is in 40 minutes").
- Then the purpose, in one or two sentences drawn from the invite, emails or notes.
- Then open threads: questions or action items from recent emails or notes.
- For a recurring meeting, add what happened last time if the notes say.
- Offer a next step, such as opening the related note or drafting an agenda. Never send anything without asking.

Keep it spoken and under 120 words unless the user asks for detail.
