
"""Helpers around Slack conversation threads.

Based on :meth:`conversations.replies` documented at
https://docs.slack.dev/reference/methods/conversations.replies/.
"""

from __future__ import annotations

import os
from typing import Dict, Iterable, Iterator, List, Optional

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


class SlackThreadClient:
	"""Tiny wrapper providing common thread operations."""

	def __init__(self, token: Optional[str] = None):
		self.token = token or os.getenv("SLACK_BOT_TOKEN") or os.getenv("SLACK_USER_TOKEN")
		if not self.token:
			raise ValueError("SLACK_BOT_TOKEN or SLACK_USER_TOKEN must be configured")
		self._client = WebClient(token=self.token)

	def fetch_thread(
		self,
		channel: str,
		thread_ts: str,
		*,
		limit: Optional[int] = None,
		include_parent: bool = True,
		latest: Optional[str] = None,
		oldest: Optional[str] = None,
	) -> List[Dict]:
		"""Return all messages in the thread, following pagination automatically."""

		messages: List[Dict] = []
		cursor: Optional[str] = None
		total_fetched = 0

		while True:
			try:
				response = self._client.conversations_replies(
					channel=channel,
					ts=thread_ts,
					cursor=cursor,
					limit=limit,
					latest=latest,
					oldest=oldest,
					inclusive=bool(latest or oldest),
				)
			except SlackApiError as exc:  # pragma: no cover
				raise RuntimeError(f"Slack API error fetching thread: {exc.response['error']}") from exc

			chunk = response.get("messages", [])
			messages.extend(chunk)
			total_fetched += len(chunk)

			if limit and total_fetched >= limit:
				break

			cursor = response.get("response_metadata", {}).get("next_cursor")
			if not cursor:
				break

		if not include_parent and messages:
			parent_ts = messages[0].get("thread_ts") or messages[0].get("ts")
			messages = [msg for msg in messages if msg.get("ts") != parent_ts]

		return messages

	def iter_replies(
		self,
		channel: str,
		thread_ts: str,
		*,
		latest: Optional[str] = None,
		oldest: Optional[str] = None,
	) -> Iterator[Dict]:
		"""Yield replies one by one, excluding the parent message."""

		for message in self.fetch_thread(
			channel,
			thread_ts,
			include_parent=False,
			latest=latest,
			oldest=oldest,
		):
			yield message

	def reply(
		self,
		channel: str,
		thread_ts: str,
		text: str,
		*,
		metadata: Optional[Dict] = None,
		blocks: Optional[Iterable[Dict]] = None,
	) -> Dict:
		"""Post a reply inside an existing thread."""

		try:
			response = self._client.chat_postMessage(
				channel=channel,
				thread_ts=thread_ts,
				text=text,
				metadata=metadata,
				blocks=list(blocks) if blocks else None,
			)
		except SlackApiError as exc:  # pragma: no cover
			raise RuntimeError(f"Slack API error posting reply: {exc.response['error']}") from exc

		return response.data


__all__ = ["SlackThreadClient"]
