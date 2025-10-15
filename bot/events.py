import logging
import os
from datetime import datetime

from bot.command import handle_command
from bot.forwarder import forward_message
from bot.helpers import parse_analysis_response, prepare_thread_content
from bot.slack_helper import SlackHelper
from library import llm, sheets

logger = logging.getLogger(__name__)

slack_bot = SlackHelper()
_llm_service = None
_sheets_client = None


def _get_llm_service():
    global _llm_service
    if _llm_service is None:
        _llm_service = llm.LLMService()
    return _llm_service


def _get_sheets_client() -> sheets.SheetsClient:
    global _sheets_client
    if _sheets_client is None:
        _sheets_client = sheets.SheetsClientFactory.create_main_client()
    return _sheets_client


ALLOWED_CHANNELS = os.getenv("ALLOWED_CHANNELS", "").split(",")
FORWARD_CHANNEL_ID = os.getenv("FORWARD_CHANNEL_ID", "").split(",")


def parse_command(text):
    """Parse command from text"""
    text_lower = text.lower()
    if "pqf" in text_lower:
        return "pqf"
    elif "resolution" in text_lower:
        return "resolution"
    elif "resolve" in text_lower:
        return "resolve"
    elif "ticket" in text_lower:
        return "ticket"
    elif "confirm bug" in text_lower or "feedback" in text_lower:
        return "confirm bug"
    return None


async def handle_app_mention(event):
    """Handle app mention events"""
    channel = event.get("channel")
    if channel not in ALLOWED_CHANNELS:
        logger.info(f"Ignored event from channel {channel} (not in allowed list)")
        return

    text = event.get("text", "")
    ts = event.get("ts")
    thread_ts = event.get("thread_ts")

    if not thread_ts or thread_ts == ts:
        # Parent message
        await handle_parent_message(event, channel, ts)
    else:
        # Reply in thread
        await handle_thread_reply(event, channel, ts, thread_ts, text)


async def handle_parent_message(event, channel, ts):
    """Handle parent messages: analyze, log, and forward."""
    # Send initial response
    slack_bot.send_message(
        channel,
        "Mohon maaf atas ketidaknyamanan yang terjadi 🙏. Terima kasih atas laporanya! Laporanmu sudah masuk ke antrian dan akan segera kami proses. Harap menunggu ya, QFolks!",
        thread_ts=ts,
    )

    thread_data = slack_bot.get_thread_data(channel, ts)
    if not thread_data:
        return

    # Analyze thread
    llm_service = _get_llm_service()
    thread_content = prepare_thread_content(thread_data)
    from bot.prompts import PQF_ANALYSIS_PROMPT

    prompt = PQF_ANALYSIS_PROMPT.format(thread_content=thread_content)
    analysis_str = llm_service.simple_completion(prompt)
    analysis = parse_analysis_response(analysis_str)

    if not analysis:
        return

    # Determine product
    product_raw = (analysis.get("product") or "").strip().lower()
    agentlabs_keywords = ["agentlabs", "llm", "intent base", "dialogflow"]
    appcenter_keywords = [
        "shopee",
        "email",
        "qcrm",
        "appcenter",
        "survey",
        "tokopedia",
        "email broadcast",
        "tiktok",
        "CSAT",
        "agent copilot",
    ]

    if any(k in product_raw for k in agentlabs_keywords):
        product_sheet = "Agentlabs"
    elif any(k in product_raw for k in appcenter_keywords):
        product_sheet = "Appcenter"
    else:
        product_sheet = "Unknown"

    # Handle based on product recognition
    parent = thread_data.get("parent_message", {})
    parent_ts = parent.get("ts")
    if not parent_ts:
        return

    dt = datetime.fromtimestamp(float(parent_ts))
    bulan = dt.month
    tahun = dt.year
    week_num = ((dt.day - 1) // 7) + 1
    quarter = (
        "Q1"
        if 1 <= bulan <= 3
        else "Q2" if 4 <= bulan <= 6 else "Q3" if 7 <= bulan <= 9 else "Q4"
    )

    if product_sheet != "Unknown":
        # Log to sheet and forward success
        sheet_name = f"{quarter} {tahun} {product_sheet}"
        sheets_client = _get_sheets_client()
        sheets_client.create_sheet_if_not_exists(sheet_name)

        permalink = thread_data.get("permalink", "")
        if "&cid=" in permalink:
            permalink = permalink.split("&cid=")[0]

        existing_links = [
            l.split("&cid=")[0] if l else l
            for l in sheets_client.get_all_links(sheet_name)
        ]
        if permalink not in existing_links:
            # Prepare and log row data
            reporting_date_time = dt.strftime("%Y-%m-%d %H:%M")
            bot_user_id = slack_bot.client.auth_test()["user_id"]
            bot_user_info = slack_bot.get_user_info(bot_user_id)
            bot_name = (
                bot_user_info.get("real_name", bot_user_info.get("name", "Bot"))
                if bot_user_info
                else "Bot"
            )

            response_time_str = "Unknown"
            for reply in thread_data.get("replies", []):
                if reply.get("user") == bot_user_id:
                    ts_reply = reply.get("ts")
                    if ts_reply:
                        dt_reply = datetime.fromtimestamp(float(ts_reply))
                        response_time_str = dt_reply.strftime("%Y-%m-%d %H:%M")
                    break

            reporter_id = analysis.get("reporter", "")
            reporter_name = "Unknown"
            if reporter_id and reporter_id != "Unknown":
                user_info = slack_bot.get_user_info(reporter_id)
                if user_info:
                    reporter_name = user_info.get(
                        "real_name", user_info.get("name", reporter_id)
                    )
                else:
                    reporter_name = reporter_id

            row_data = {
                "from": "Eksternal",
                "type": analysis.get("type", "Unknown"),
                "product": analysis.get("product", "Unknown"),
                "role": "",
                "fitur": analysis.get("fitur", "Unknown"),
                "reporter": reporter_name,
                "reporting_date_time": reporting_date_time,
                "responder": bot_name,
                "description": analysis.get("description", "No description"),
                "link": permalink,
                "response_time": response_time_str,
                "severity": "",
                "urgency": "",
            }
            sheets_client.prepend_row(row_data, sheet_name)

        forward_message(
            slack_bot.client, thread_data, quarter, tahun, week_num, dt, success=True
        )
    else:
        # Forward as not recorded
        forward_message(
            slack_bot.client, thread_data, quarter, tahun, week_num, dt, success=False
        )


async def handle_thread_reply(event, channel, ts, thread_ts, text):
    """Handle replies in threads: parse command and execute."""
    thread_data = slack_bot.get_thread_data(channel, thread_ts)

    command = parse_command(text)
    if command:
        if command == "pqf" and channel not in FORWARD_CHANNEL_ID:
            slack_bot.send_message(
                channel, "PQF command not allowed in this channel.", thread_ts=ts
            )
            return
        result = handle_command(
            command, channel, thread_ts, thread_data, slack_bot.client, text
        )
        slack_bot.send_message(channel, result, thread_ts=ts)
    else:
        help_message = """
        Saat ini bot tidak dapat menindaklanjuti issue melalui kolom komentar. Informasi terkait bug/issue/feedback tersebut sudah kami terima dan sedang diproses oleh tim kami. Pembaruan dan respon akan disampaikan oleh tim kami setelah ada perkembangan lebih lanjut. Terimakasih.
        """
        slack_bot.send_message(channel, help_message, thread_ts=ts)
