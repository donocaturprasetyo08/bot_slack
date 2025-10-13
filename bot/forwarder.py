# Forwarder utilities for Slack bot

import os
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

def forward_message(
    slack_client,
    thread_data: dict,
    quarter: str,
    tahun: int,
    week_num: int,
    dt: datetime,
    success: bool = True,
    extra_text: Optional[str] = None
) -> bool:
    """Forward a message to the configured channel.

    Args:
        slack_client: Slack WebClient instance.
        thread_data: Thread data dict with 'permalink'.
        quarter: Quarter string like 'Q1'.
        tahun: Year as int.
        week_num: Week number.
        dt: Datetime object for date info.
        success: Whether the operation was successful.
        extra_text: Optional extra text to append.

    Returns:
        True if forwarded successfully, False otherwise.
    """
    try:
        forward_channel = os.getenv('FORWARD_CHANNEL_ID')
        if not forward_channel:
            logger.info("No FORWARD_CHANNEL_ID set, skipping forward")
            return False

        permalink = thread_data.get('permalink', '')
        if '&cid=' in permalink:
            permalink = permalink.split('&cid=')[0]

        status = "Tercatat" if success else "Tidak Tercatat"
        month_name = dt.strftime('%B')
        info_text = f"[{quarter}] [{tahun}] [Week {week_num}] [Date {dt.day} - {month_name}] [{status}]"
        if extra_text:
            info_text += extra_text

        slack_client.chat_postMessage(
            channel=forward_channel,
            text=info_text + "\n" + permalink
        )
        logger.info(f"Forwarded message to {forward_channel}: {info_text}")
        return True
    except Exception as e:
        logger.error(f"Failed to forward message: {e}")
        return False