"""Helpers for Slack Lists API operations.

These wrappers favour Slack's official Web API endpoints documented at
https://docs.slack.dev/reference/methods/slackLists.items.info.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from config import config


def _clean_payload(**kwargs: Any) -> Dict[str, Any]:
    """Drop keys that contain ``None`` so calls stay compact."""

    return {key: value for key, value in kwargs.items() if value is not None}


class SlackListClient:
    """Slim client for Slack Lists CRUD operations."""

    def __init__(self, token: Optional[str] = None):
        self.token = token or config.slack_user_token or config.slack_bot_token
        if not self.token:
            raise ValueError(
                "Provide SLACK_USER_TOKEN or SLACK_BOT_TOKEN for Slack Lists access"
            )
        self._client = WebClient(token=self.token)

    def _api_call(self, method: str, **payload: Any) -> Dict[str, Any]:
        try:
            response = self._client.api_call(method, json=_clean_payload(**payload))
        except SlackApiError as exc:  # pragma: no cover - we surface a richer error
            raise RuntimeError(
                f"Slack API error calling {method}: {exc.response['error']}"
            ) from exc

        if not response.get("ok", False):
            raise RuntimeError(
                f"Slack API error calling {method}: {response.get('error')}"
            )
        return response

    def get_item(
        self, list_id: str, item_id: str, *, team_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Return metadata for a list item."""

        response = self._api_call(
            "slacklists.items.info",
            list_id=list_id,
            item_id=item_id,
            team_id=team_id,
        )
        return response.get("item", response)

    def list_items(
        self,
        list_id: str,
        *,
        cursor: Optional[str] = None,
        limit: Optional[int] = None,
        team_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return the raw payload from ``slacklists.items.list``."""

        return self._api_call(
            "slacklists.items.list",
            list_id=list_id,
            cursor=cursor,
            limit=limit,
            team_id=team_id,
        )

    def iter_items(
        self,
        list_id: str,
        *,
        team_id: Optional[str] = None,
        page_size: Optional[int] = None,
    ) -> Iterable[Dict[str, Any]]:
        """Yield every item for ``list_id`` by following cursors."""

        cursor = None
        while True:
            response = self.list_items(
                list_id, cursor=cursor, limit=page_size, team_id=team_id
            )
            for item in response.get("items", []):
                yield item
            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

    def create_item(
        self,
        list_id: str,
        title: str,
        *,
        description: Optional[str] = None,
        emoji: Optional[str] = None,
        url: Optional[str] = None,
        team_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new list item."""

        response = self._api_call(
            "slacklists.items.create",
            list_id=list_id,
            title=title,
            description=description,
            emoji=emoji,
            url=url,
            team_id=team_id,
        )
        return response.get("item", response)

    def update_item(
        self,
        list_id: str,
        item_id: str,
        *,
        title: Optional[str] = None,
        description: Optional[str] = None,
        emoji: Optional[str] = None,
        url: Optional[str] = None,
        team_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update an existing list item."""

        response = self._api_call(
            "slacklists.items.update",
            list_id=list_id,
            item_id=item_id,
            title=title,
            description=description,
            emoji=emoji,
            url=url,
            team_id=team_id,
        )
        return response.get("item", response)

    def delete_item(
        self, list_id: str, item_id: str, *, team_id: Optional[str] = None
    ) -> bool:
        """Delete a list item."""

        response = self._api_call(
            "slacklists.items.delete",
            list_id=list_id,
            item_id=item_id,
            team_id=team_id,
        )
        return response.get("ok", False)


__all__ = ["SlackListClient"]
