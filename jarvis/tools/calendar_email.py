"""AppleScript-based access to macOS Calendar.app and Mail.app."""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from jarvis.tools.mac_control import run_applescript, _escape_applescript

logger = logging.getLogger("jarvis.tools.calendar_email")


async def get_upcoming_events(days: int = 1) -> str:
    """Get upcoming calendar events for the next N days (1-14 days)."""
    days = max(1, min(days, 14))

    script = f'''
    set output to ""
    set today to current date
    set endDate to today + ({days} * days)

    tell application "Calendar"
        set allCals to every calendar
        set eventList to {{}}

        repeat with cal in allCals
            set calName to name of cal
            try
                set evts to (every event of cal whose start date >= today and start date < endDate)
                repeat with evt in evts
                    set evtStart to start date of evt
                    set evtEnd to end date of evt
                    set evtTitle to summary of evt
                    set evtLoc to ""
                    try
                        set evtLoc to location of evt
                    end try
                    set evtNotes to ""
                    try
                        set evtNotes to description of evt
                        if evtNotes is missing value then set evtNotes to ""
                    end try
                    set evtAllDay to allday event of evt

                    if evtAllDay then
                        set timeStr to "All Day"
                    else
                        set timeStr to (evtStart as string) & " - " & (evtEnd as string)
                    end if

                    set evtLine to (evtTitle & " | " & timeStr & " | Calendar: " & calName) as string
                    if evtLoc is not "" and evtLoc is not missing value then
                        set evtLine to evtLine & " | Location: " & evtLoc
                    end if
                    if evtNotes is not "" and length of evtNotes > 0 then
                        set notesPreview to text 1 thru (min of {{100, length of evtNotes}}) of evtNotes
                        set evtLine to evtLine & " | Notes: " & notesPreview
                    end if

                    set output to output & evtLine & linefeed
                end repeat
            on error errMsg
            end try
        end repeat
    end tell

    if output is "" then
        return "No events found in the next {days} day(s)."
    else
        return output
    end if
    '''

    result = await run_applescript(script)
    if result.startswith("Error:"):
        return f"Could not read calendar: {result}. Make sure Calendar.app has been opened at least once."
    return result


async def create_calendar_event(
    title: str,
    start_date: str,
    end_date: str = "",
    location: str = "",
    notes: str = "",
    calendar_name: str = "",
    all_day: bool = False,
) -> str:
    """Create a new calendar event."""
    title_safe = _escape_applescript(title)
    location_safe = _escape_applescript(location)
    notes_safe = _escape_applescript(notes)

    start_safe = _escape_applescript(start_date)
    end_safe = _escape_applescript(end_date) if end_date else ""
    cal_safe = _escape_applescript(calendar_name) if calendar_name else ""

    if all_day:
        date_setup = f'''
        set evtStart to date "{start_safe}"
        set time of evtStart to 0
        set evtEnd to evtStart + (1 * days)
        '''
    elif end_date:
        date_setup = f'''
        set evtStart to date "{start_safe}"
        set evtEnd to date "{end_safe}"
        '''
    else:
        date_setup = f'''
        set evtStart to date "{start_safe}"
        set evtEnd to evtStart + (1 * hours)
        '''

    if calendar_name:
        cal_target = f'calendar "{cal_safe}"'
    else:
        cal_target = 'first calendar'

    script = f'''
    tell application "Calendar"
        {date_setup}

        tell {cal_target}
            set newEvent to make new event with properties {{summary:"{title_safe}", start date:evtStart, end date:evtEnd, allday event:{str(all_day).lower()}}}

            if "{location_safe}" is not "" then
                set location of newEvent to "{location_safe}"
            end if

            if "{notes_safe}" is not "" then
                set description of newEvent to "{notes_safe}"
            end if
        end tell
    end tell

    return "Event created: {title_safe}"
    '''

    result = await run_applescript(script)
    if result.startswith("Error:"):
        return f"Could not create event: {result}. Check that the date format is correct (e.g., 'March 25, 2026 2:00 PM')."
    return result


async def get_calendar_list() -> str:
    """List all available calendars."""
    script = '''
    set output to ""
    tell application "Calendar"
        repeat with cal in every calendar
            set calName to name of cal
            set calColor to ""
            try
                set calColor to color of cal as string
            end try
            set output to output & calName & linefeed
        end repeat
    end tell
    if output is "" then
        return "No calendars found."
    else
        return output
    end if
    '''

    result = await run_applescript(script)
    if result.startswith("Error:"):
        return f"Could not list calendars: {result}"
    return result


async def search_calendar_events(query: str, days: int = 30) -> str:
    """Search for calendar events by title within the next N days (1-90 days)."""
    days = max(1, min(days, 90))
    query_safe = _escape_applescript(query).lower()

    script = f'''
    set output to ""
    set today to current date
    set endDate to today + ({days} * days)
    set searchTerm to "{query_safe}"

    tell application "Calendar"
        repeat with cal in every calendar
            set calName to name of cal
            try
                set evts to (every event of cal whose start date >= today and start date < endDate)
                repeat with evt in evts
                    set evtTitle to summary of evt
                    if (evtTitle as string) contains searchTerm then
                        set evtStart to start date of evt
                        set evtLine to evtTitle & " | " & (evtStart as string) & " | Calendar: " & calName
                        set output to output & evtLine & linefeed
                    end if
                end repeat
            on error
            end try
        end repeat
    end tell

    if output is "" then
        return "No events matching '{query_safe}' found in the next {days} days."
    else
        return output
    end if
    '''

    result = await run_applescript(script)
    if result.startswith("Error:"):
        return f"Calendar search failed: {result}"
    return result


async def get_recent_emails(count: int = 10, mailbox: str = "INBOX") -> str:
    """Get recent emails from Mail.app (up to 25 messages)."""
    count = max(1, min(count, 25))

    script = f'''
    set output to ""
    set msgCount to 0

    tell application "Mail"
        set allAccounts to every account
        repeat with acct in allAccounts
            try
                set mb to mailbox "{mailbox}" of acct
                set msgs to messages of mb
                set totalMsgs to count of msgs
                set startIdx to 1
                if totalMsgs > {count} - msgCount then
                    set startIdx to totalMsgs - ({count} - msgCount) + 1
                end if

                repeat with i from totalMsgs to startIdx by -1
                    if msgCount >= {count} then exit repeat
                    set msg to message i of mb
                    set msgSubject to subject of msg
                    set msgSender to sender of msg
                    set msgDate to date received of msg
                    set msgRead to read status of msg

                    set readFlag to ""
                    if not msgRead then set readFlag to "[UNREAD] "

                    set msgPreview to ""
                    try
                        set msgContent to content of msg
                        if msgContent is not missing value and length of msgContent > 0 then
                            set previewLen to min of {{150, length of msgContent}}
                            set msgPreview to text 1 thru previewLen of msgContent
                        end if
                    end try

                    set msgLine to readFlag & "From: " & msgSender & " | Subject: " & msgSubject & " | Date: " & (msgDate as string)
                    if msgPreview is not "" then
                        set msgLine to msgLine & " | Preview: " & msgPreview
                    end if

                    set output to output & msgLine & linefeed
                    set msgCount to msgCount + 1
                end repeat
            on error errMsg
                -- Skip accounts where the mailbox doesn't exist
            end try
        end repeat
    end tell

    if output is "" then
        return "No emails found in {mailbox}. Mail.app may need to be opened and synced first."
    else
        return "Recent emails (" & msgCount & " messages):" & linefeed & output
    end if
    '''

    result = await run_applescript(script)
    if result.startswith("Error:"):
        return f"Could not read emails: {result}. Make sure Mail.app is set up with an account."
    return result


async def get_unread_count() -> str:
    """Get the count of unread emails across all accounts."""
    script = '''
    set output to ""
    set totalUnread to 0

    tell application "Mail"
        repeat with acct in every account
            set acctName to name of acct
            try
                set mb to mailbox "INBOX" of acct
                set unreadMsgs to (messages of mb whose read status is false)
                set unreadCount to count of unreadMsgs
                set totalUnread to totalUnread + unreadCount
                if unreadCount > 0 then
                    set output to output & acctName & ": " & unreadCount & " unread" & linefeed
                end if
            on error
            end try
        end repeat
    end tell

    if totalUnread is 0 then
        return "No unread emails. Inbox zero!"
    else
        return "Unread emails (" & totalUnread & " total):" & linefeed & output
    end if
    '''

    result = await run_applescript(script)
    if result.startswith("Error:"):
        return f"Could not check unread count: {result}"
    return result


async def send_email(
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
) -> str:
    """Compose and send an email via Mail.app."""
    subject_safe = _escape_applescript(subject)
    body_safe = _escape_applescript(body)
    to_safe = _escape_applescript(to)

    to_recipients = ""
    for addr in to_safe.split(","):
        addr = addr.strip()
        if addr:
            to_recipients += f'make new to recipient at end of to recipients with properties {{address:"{addr}"}}\n'

    cc_recipients = ""
    if cc:
        for addr in cc.split(","):
            addr = _escape_applescript(addr.strip())
            if addr:
                cc_recipients += f'make new cc recipient at end of cc recipients with properties {{address:"{addr}"}}\n'

    bcc_recipients = ""
    if bcc:
        for addr in bcc.split(","):
            addr = _escape_applescript(addr.strip())
            if addr:
                bcc_recipients += f'make new bcc recipient at end of bcc recipients with properties {{address:"{addr}"}}\n'

    script = f'''
    tell application "Mail"
        set newMessage to make new outgoing message with properties {{subject:"{subject_safe}", content:"{body_safe}", visible:false}}

        tell newMessage
            {to_recipients}
            {cc_recipients}
            {bcc_recipients}
        end tell

        send newMessage
    end tell

    return "Email sent to {to_safe} with subject: {subject_safe}"
    '''

    result = await run_applescript(script)
    if result.startswith("Error:"):
        return f"Could not send email: {result}. Make sure Mail.app is configured with an outgoing mail account."

    logger.info("Email sent to %s: '%s'", to, subject[:50])
    return result


async def search_emails(query: str, count: int = 10) -> str:
    """Search for emails by subject or sender in Mail.app (up to 25 results)."""
    count = max(1, min(count, 25))
    query_safe = _escape_applescript(query).lower()

    script = f'''
    set output to ""
    set resultCount to 0
    set searchTerm to "{query_safe}"

    tell application "Mail"
        repeat with acct in every account
            try
                set mb to mailbox "INBOX" of acct
                set msgs to messages of mb
                set totalMsgs to count of msgs

                repeat with i from totalMsgs to 1 by -1
                    if resultCount >= {count} then exit repeat
                    set msg to message i of mb

                    set msgSubject to subject of msg
                    set msgSender to sender of msg
                    set subjectLower to msgSubject as string

                    if subjectLower contains searchTerm or (msgSender as string) contains searchTerm then
                        set msgDate to date received of msg
                        set msgLine to "From: " & msgSender & " | Subject: " & msgSubject & " | Date: " & (msgDate as string)
                        set output to output & msgLine & linefeed
                        set resultCount to resultCount + 1
                    end if
                end repeat
            on error
            end try
        end repeat
    end tell

    if output is "" then
        return "No emails matching '{query_safe}' found."
    else
        return "Found " & resultCount & " matching email(s):" & linefeed & output
    end if
    '''

    result = await run_applescript(script)
    if result.startswith("Error:"):
        return f"Email search failed: {result}"
    return result


async def read_email(subject_search: str) -> str:
    """Read the full content of a specific email by searching for its subject."""
    query_safe = _escape_applescript(subject_search).lower()

    script = f'''
    set searchTerm to "{query_safe}"
    set output to "Email not found."

    tell application "Mail"
        repeat with acct in every account
            try
                set mb to mailbox "INBOX" of acct
                set msgs to messages of mb
                set totalMsgs to count of msgs

                repeat with i from totalMsgs to 1 by -1
                    set msg to message i of mb
                    set msgSubject to (subject of msg) as string

                    if msgSubject contains searchTerm then
                        set msgSender to sender of msg
                        set msgDate to date received of msg
                        set msgTo to ""
                        try
                            set toRecips to to recipients of msg
                            repeat with r in toRecips
                                set msgTo to msgTo & (address of r) & ", "
                            end repeat
                        end try

                        set msgBody to ""
                        try
                            set msgBody to content of msg
                            if msgBody is missing value then set msgBody to "(no text content)"
                            if length of msgBody > 3000 then
                                set msgBody to text 1 thru 3000 of msgBody & "... (truncated)"
                            end if
                        end try

                        set output to "From: " & msgSender & linefeed & "To: " & msgTo & linefeed & "Date: " & (msgDate as string) & linefeed & "Subject: " & msgSubject & linefeed & linefeed & msgBody
                        exit repeat
                    end if
                end repeat
            on error
            end try
            if output is not "Email not found." then exit repeat
        end repeat
    end tell

    return output
    '''

    result = await run_applescript(script)
    if result.startswith("Error:"):
        return f"Could not read email: {result}"
    return result
