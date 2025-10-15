# Command handlers for Slack bot

import logging
from datetime import datetime
from typing import Optional

from bot.forwarder import forward_message
from bot.helpers import (
    get_sheet_name,
    parse_analysis_response,
    parse_slack_permalink,
    prepare_thread_content,
    validate_and_extract_command,
)
from bot.prompts import (
    BUG_ANALYSIS,
    BUG_CONFIRMATION_PROMPT,
    COMMAND_UNKNOWN,
    FAILED_BUG,
    FAILED_PQF,
    FAILED_RESOLUTION,
    FAILED_TICKET,
    LOG_SUCCESS,
    NO_THREAD_DATA,
    NO_THREAD_FOUND,
    PQF_ANALYSIS_PROMPT,
    RESOLUTION_UPDATED,
    TICKET_CREATED,
)
from config import config
from library import llm, sheets, slack_thread, slacklist

logger = logging.getLogger(__name__)

# Global clients (lazy init)
_slack_thread_client: Optional[slack_thread.SlackThreadClient] = None
_sheets_client: Optional[sheets.SheetsClient] = None
_llm_service: Optional[llm.LLMService] = None
_slack_list_client: Optional[slacklist.SlackListClient] = None


def _get_slack_thread_client() -> slack_thread.SlackThreadClient:
    global _slack_thread_client
    if _slack_thread_client is None:
        _slack_thread_client = slack_thread.SlackThreadClient()
    return _slack_thread_client


def _get_sheets_client() -> sheets.SheetsClient:
    global _sheets_client
    if _sheets_client is None:
        _sheets_client = sheets.SheetsClient()
    return _sheets_client


def _get_llm_service() -> llm.LLMService:
    global _llm_service
    if _llm_service is None:
        _llm_service = llm.LLMService()
    return _llm_service


def _get_slack_list_client() -> slacklist.SlackListClient:
    global _slack_list_client
    if _slack_list_client is None:
        _slack_list_client = slacklist.SlackListClient()
    return _slack_list_client


def handle_pqf(
    channel: str,
    thread_ts: str,
    thread_data: dict = None,
    slack_client=None,
    from_value: str = "Internal",
    product: str = "AgentLabs",
) -> str:
    """Handle PQF command: Analyze thread, log to sheets, and forward."""
    try:
        if not thread_data:
            return NO_THREAD_DATA

        sheet_name = get_sheet_name(from_value, product)

        # Check if already logged
        permalink = thread_data.get("permalink", "")
        if "&cid=" in permalink:
            permalink = permalink.split("&cid=")[0]
        existing_links = [
            l.split("&cid=")[0] if l else l
            for l in _get_sheets_client().get_all_links(sheet_name)
        ]
        if permalink in existing_links:
            return "Thread already logged."

        # Analyze with LLM
        thread_content = prepare_thread_content(thread_data)
        prompt = PQF_ANALYSIS_PROMPT.format(thread_content=thread_content)
        llm_service = _get_llm_service()
        analysis_str = llm_service.simple_completion(prompt)
        analysis = parse_analysis_response(analysis_str)

        # Log to sheets
        sheets_client = _get_sheets_client()
        # Prepare row data similar to apps.py
        row_data = [
            analysis.get("type", ""),
            analysis.get("product", ""),
            analysis.get("fitur", ""),
            analysis.get("description", ""),
            analysis.get("role", ""),
            analysis.get("reporter", ""),
            analysis.get("responder", ""),
            analysis.get("severity", ""),
            analysis.get("urgency", ""),
            permalink,
            "",  # notes
        ]
        sheets_client.append_rows(f"{sheet_name}!A:A", [row_data])

        # Forward success message
        if slack_client and thread_data:
            parent = thread_data.get("parent_message", {})
            parent_ts = parent.get("ts")
            if parent_ts:
                dt = datetime.fromtimestamp(float(parent_ts))
                bulan = dt.month
                tahun = dt.year
                week_num = ((dt.day - 1) // 7) + 1
                if 1 <= bulan <= 3:
                    quarter = "Q1"
                elif 4 <= bulan <= 6:
                    quarter = "Q2"
                elif 7 <= bulan <= 9:
                    quarter = "Q3"
                else:
                    quarter = "Q4"
                forward_message(
                    slack_client,
                    thread_data,
                    quarter,
                    tahun,
                    week_num,
                    dt,
                    success=True,
                )

        return LOG_SUCCESS.format(analysis=str(analysis))
    except Exception as e:
        logger.error(f"Error in PQF: {e}")
        return FAILED_PQF


def handle_resolution(
    channel: str,
    thread_ts: str,
    thread_data: dict = None,
    slack_client=None,
    resolution: str = "Unknown",
) -> str:
    """Handle resolution command: Update resolution in sheets."""
    try:
        if not thread_data:
            return NO_THREAD_DATA

        permalink = thread_data.get("permalink", "")
        if "&cid=" in permalink:
            permalink = permalink.split("&cid=")[0]

        # Find sheet containing the link
        sheets_client = _get_sheets_client()
        found = False
        for sheet_name in sheets_client.get_available_sheets():
            links = [
                l.split("&cid=")[0] if l else l
                for l in sheets_client.get_all_links(sheet_name)
            ]
            if permalink in links:
                # Update resolution (assuming column for resolution)
                # For simplicity, append to a resolution column, but in apps.py it's more complex
                sheets_client.append_rows(
                    f"{sheet_name}!J:J", [[resolution]]
                )  # Assuming column J is resolution
                found = True
                break

        if not found:
            return "Thread not found in sheets."

        # Forward if possible
        if slack_client and thread_data:
            parent = thread_data.get("parent_message", {})
            parent_ts = parent.get("ts")
            if parent_ts:
                dt = datetime.fromtimestamp(float(parent_ts))
                bulan = dt.month
                tahun = dt.year
                week_num = ((dt.day - 1) // 7) + 1
                if 1 <= bulan <= 3:
                    quarter = "Q1"
                elif 4 <= bulan <= 6:
                    quarter = "Q2"
                elif 7 <= bulan <= 9:
                    quarter = "Q3"
                else:
                    quarter = "Q4"
                forward_message(
                    slack_client,
                    thread_data,
                    quarter,
                    tahun,
                    week_num,
                    dt,
                    success=True,
                )

        return RESOLUTION_UPDATED.format(resolution=resolution)
    except Exception as e:
        logger.error(f"Error in resolution: {e}")
        return FAILED_RESOLUTION


def handle_resolve(
    channel: str, thread_ts: str, thread_data: dict = None, slack_client=None
) -> str:
    """Handle resolve command: Mark as resolved in sheets."""
    return handle_resolution(channel, thread_ts, thread_data, slack_client, "Resolved")


def handle_ticket(
    channel: str,
    thread_ts: str,
    thread_data: dict = None,
    slack_client=None,
    title: str = "New Ticket",
) -> str:
    """Handle ticket command: Create a ticket in sheets."""
    try:
        if not thread_data:
            return NO_THREAD_DATA

        parent_forward = thread_data.get("parent_message", {})
        if (
            parent_forward
            and parent_forward.get("permalink")
            and parent_forward.get("ts")
        ):
            permalink = parent_forward.get("permalink")
            thread_ts_real = parent_forward.get("ts")
            channel_real, _ = parse_slack_permalink(permalink.split("?")[0])
        else:
            return "No valid permalink in thread."

        if not channel_real or not thread_ts_real:
            return "Failed to parse permalink."

        # Fetch real thread_data
        client = _get_slack_thread_client()
        real_thread_data = client.get_thread_data(channel_real, thread_ts_real)
        if not real_thread_data:
            return NO_THREAD_FOUND

        parent = real_thread_data.get("parent_message", {})

        # Analyze
        thread_content = prepare_thread_content(real_thread_data)
        prompt = PQF_ANALYSIS_PROMPT.format(thread_content=thread_content)
        llm_service = _get_llm_service()
        analysis_str = llm_service.simple_completion(prompt)
        analysis = parse_analysis_response(analysis_str) or {}

        # Get reporter name
        reporter_name = "Unknown"
        parent_user_id = parent.get("user")
        if parent_user_id and slack_client:
            try:
                user_info = slack_client.users_info(user=parent_user_id)
                reporter_name = user_info["user"]["real_name"]
            except:
                pass

        # Generate code
        sheets_client = _get_sheets_client()
        sheet_name = config.bug_sheet_name
        existing_codes = sheets_client.get_all_codes(
            sheet_name
        )  # Assume method exists or simplify
        code_num = len(existing_codes) + 1
        code_str = f"QR-{code_num:03d}"

        # Prepare row
        reporting_date_time = ""
        parent_ts = parent.get("ts")
        if parent_ts:
            dt = datetime.fromtimestamp(float(parent_ts))
            reporting_date_time = dt.strftime("%Y-%m-%d %H:%M")

        row_data = {
            "from": "Eksternal",
            "type": analysis.get("type", ""),
            "code": code_str,
            "product": analysis.get("product", ""),
            "role": analysis.get("role", ""),
            "fitur": analysis.get("fitur", ""),
            "reporter": reporter_name,
            "reporting_date_time": reporting_date_time,
            "deskripsi": analysis.get("description", ""),
            "step reproduce": "",
            "severity": analysis.get("severity", ""),
            "urgency": analysis.get("urgency", ""),
            "assignee": "",
            "status": "",
            "scheduled release on": "",
            "link": permalink,
            "note": "",
        }
        sheets_client.append_rows(f"{sheet_name}!A:A", [list(row_data.values())])

        # Forward
        if slack_client and thread_data:
            if parent_ts:
                dt = datetime.fromtimestamp(float(parent_ts))
                bulan = dt.month
                tahun = dt.year
                week_num = ((dt.day - 1) // 7) + 1
                if 1 <= bulan <= 3:
                    quarter = "Q1"
                elif 4 <= bulan <= 6:
                    quarter = "Q2"
                elif 7 <= bulan <= 9:
                    quarter = "Q3"
                else:
                    quarter = "Q4"
                forward_message(
                    slack_client,
                    thread_data,
                    quarter,
                    tahun,
                    week_num,
                    dt,
                    success=True,
                )

        return TICKET_CREATED.format(item_id=code_str)
    except Exception as e:
        logger.error(f"Error in ticket: {e}")
        return FAILED_TICKET


def handle_confirm_bug(
    channel: str,
    thread_ts: str,
    thread_data: dict = None,
    slack_client=None,
    from_value: str = "Internal",
) -> str:
    """Handle confirm bug/feedback: Analyze with LLM and confirm."""
    try:
        if not thread_data:
            return NO_THREAD_DATA

        client = _get_slack_thread_client()
        messages = client.fetch_thread(channel, thread_ts)
        if not messages:
            return NO_THREAD_FOUND

        thread_text = "\n".join([msg.get("text", "") for msg in messages])
        prompt = BUG_CONFIRMATION_PROMPT.format(thread_text=thread_text)

        llm_service = _get_llm_service()
        analysis = llm_service.simple_completion(prompt)

        sheet_name = get_sheet_name(from_value, "AgentLabs")  # Default product, or pass
        sheets_client = _get_sheets_client()
        sheets_client.append_rows(f"{sheet_name}!A:B", [[thread_ts, analysis]])

        # Forward if possible
        if slack_client and thread_data:
            parent = thread_data.get("parent_message", {})
            parent_ts = parent.get("ts")
            if parent_ts:
                dt = datetime.fromtimestamp(float(parent_ts))
                bulan = dt.month
                tahun = dt.year
                week_num = ((dt.day - 1) // 7) + 1
                if 1 <= bulan <= 3:
                    quarter = "Q1"
                elif 4 <= bulan <= 6:
                    quarter = "Q2"
                elif 7 <= bulan <= 9:
                    quarter = "Q3"
                else:
                    quarter = "Q4"
                forward_message(
                    slack_client,
                    thread_data,
                    quarter,
                    tahun,
                    week_num,
                    dt,
                    success=True,
                )

        return BUG_ANALYSIS.format(analysis=analysis)
    except Exception as e:
        logger.error(f"Error in confirm bug: {e}")
        return FAILED_BUG


def handle_command(
    command: str,
    channel: str = "",
    thread_ts: str = "",
    thread_data: dict = None,
    slack_client=None,
    text: str = "",
    **kwargs,
) -> str:
    """Handle a bot command and return a response."""
    command = command.lower()

    if command == "pqf":
        from_value, product, error = validate_and_extract_command(text)
        if error:
            return error
        return handle_pqf(
            channel, thread_ts, thread_data, slack_client, from_value, product
        )
    elif command == "resolution":
        resolution = kwargs.get("resolution", "Unknown")
        return handle_resolution(
            channel, thread_ts, thread_data, slack_client, resolution
        )
    elif command == "resolve":
        return handle_resolve(channel, thread_ts, thread_data, slack_client)
    elif command == "ticket":
        title = kwargs.get("title", "New Ticket")
        return handle_ticket(channel, thread_ts, thread_data, slack_client, title)
    elif command in ("confirm bug", "feedback"):
        from_value, _, _ = validate_and_extract_command(text)
        if not from_value:
            from_value = "Internal"
        return handle_confirm_bug(
            channel, thread_ts, thread_data, slack_client, from_value
        )
    else:
        return COMMAND_UNKNOWN
