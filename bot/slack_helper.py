# Slack helper utilities

import logging
import time
from datetime import datetime

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from config import config

logger = logging.getLogger(__name__)


class SlackHelper:
    def __init__(self):
        """Initialize Slack helper"""
        self.token = config.slack_bot_token
        self.client = WebClient(token=self.token)

    def send_message(self, channel, text, thread_ts=None):
        """Send message to Slack channel"""
        try:
            response = self.client.chat_postMessage(
                channel=channel, text=text, thread_ts=thread_ts
            )
            return response
        except SlackApiError as e:
            logger.error(f"Error sending message: {e.response['error']}")
            return None

    def get_thread_data(self, channel, ts, max_retries=3):
        """Get thread data from Slack, with rate limit handling and exponential backoff"""
        logger.info(f"[get_thread_data] Called with channel={channel}, ts={ts}")
        try:
            # Dapatkan thread_ts dari event (bisa parent atau reply)
            thread_ts = ts
            wait = 5
            for attempt in range(max_retries):
                try:
                    response = self.client.conversations_replies(channel=channel, ts=ts)
                    break
                except SlackApiError as e:
                    if e.response["error"] == "ratelimited":
                        retry_after = int(e.response.headers.get("Retry-After", wait))
                        logger.warning(
                            f"Rate limited on conversations_replies. Waiting {retry_after} seconds (attempt {attempt+1}/{max_retries})..."
                        )
                        time.sleep(retry_after)
                        wait = min(
                            retry_after * 2, 600
                        )  # Exponential backoff, max 10 menit
                        continue
                    else:
                        logger.error(
                            f"Error getting thread data: {e.response['error']}"
                        )
                        return None
            else:
                logger.error("Max retries exceeded for conversations_replies")
                return None
            messages_first = response.get("messages") or []
            if response.get("ok") and messages_first:
                thread_ts = messages_first[0].get("thread_ts", ts)

            # Ambil semua pesan di thread (paginasi jika perlu)
            all_messages = []
            cursor = None
            while True:
                wait = 5
                for attempt in range(max_retries):
                    try:
                        resp = self.client.conversations_replies(
                            channel=channel, ts=thread_ts, cursor=cursor
                        )
                        break
                    except SlackApiError as e:
                        if e.response["error"] == "ratelimited":
                            retry_after = int(
                                e.response.headers.get("Retry-After", wait)
                            )
                            logger.warning(
                                f"Rate limited on conversations_replies (pagination). Waiting {retry_after} seconds (attempt {attempt+1}/{max_retries})..."
                            )
                            time.sleep(retry_after)
                            wait = min(retry_after * 2, 600)
                            continue
                        else:
                            logger.error(
                                f"Error getting thread data: {e.response['error']}"
                            )
                            return None
                else:
                    logger.error(
                        "Max retries exceeded for conversations_replies (pagination)"
                    )
                    return None
                if not resp.get("ok"):
                    logger.error(f"Error getting thread data: {resp.get('error')}")
                    return None
                messages = resp.get("messages") or []
                all_messages.extend(messages)
                if not resp.get("has_more"):
                    break
                cursor = resp.get("response_metadata", {}).get("next_cursor")

            # Parent = pesan dengan ts == thread_ts
            parent_message = next(
                (m for m in all_messages if m["ts"] == thread_ts), all_messages[0]
            )
            replies = [m for m in all_messages if m["ts"] != thread_ts]

            # Get permalink
            wait = 5
            for attempt in range(max_retries):
                try:
                    permalink_response = self.client.chat_getPermalink(
                        channel=channel, message_ts=thread_ts
                    )
                    break
                except SlackApiError as e:
                    if e.response["error"] == "ratelimited":
                        retry_after = int(e.response.headers.get("Retry-After", wait))
                        logger.warning(
                            f"Rate limited on chat_getPermalink. Waiting {retry_after} seconds (attempt {attempt+1}/{max_retries})..."
                        )
                        time.sleep(retry_after)
                        wait = min(retry_after * 2, 600)
                        continue
                    else:
                        logger.error(f"Error getting permalink: {e.response['error']}")
                        return None
            else:
                logger.error("Max retries exceeded for chat_getPermalink")
                return None
            permalink = (
                permalink_response.get("permalink", "")
                if permalink_response.get("ok")
                else ""
            )

            # Compile thread data
            thread_data = {
                "timestamp": datetime.fromtimestamp(float(thread_ts)).isoformat(),
                "channel": channel,
                "parent_message": {
                    "text": parent_message.get("text", ""),
                    "user": parent_message.get("user", ""),
                    "ts": parent_message.get("ts", ""),
                },
                "replies": [
                    {
                        "text": r.get("text", ""),
                        "user": r.get("user", ""),
                        "ts": r.get("ts", ""),
                    }
                    for r in replies
                ],
                "permalink": permalink,
                "message_count": len(all_messages),
            }
            # Get user info for parent message
            if parent_message.get("user"):
                user_info = self.get_user_info(parent_message["user"])
                thread_data["user"] = (
                    user_info.get("real_name", user_info.get("name", ""))
                    if user_info
                    else parent_message["user"]
                )
            return thread_data
        except SlackApiError as e:
            logger.error(f"Error getting thread data: {e.response['error']}")
            return None

    def get_user_info(self, user_id):
        """Get user information"""
        try:
            response = self.client.users_info(user=user_id)
            if response["ok"]:
                return response["user"]
            return None
        except SlackApiError as e:
            logger.error(f"Error getting user info: {e.response['error']}")
            return None

    def users_info(self, user):
        """Alias for client.users_info"""
        return self.client.users_info(user=user)
