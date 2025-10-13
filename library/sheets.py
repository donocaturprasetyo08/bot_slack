
"""Google Sheets helper built on top of the official API quickstart.

See https://developers.google.com/workspace/sheets/api/quickstart/python for
the reference implementation that inspired this module.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Dict, Iterable, List, Optional, Sequence

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class SheetsClient:
	"""Thin Google Sheets client for reading and writing values."""

	def __init__(
		self,
		spreadsheet_id: Optional[str] = None,
		*,
		credentials_json: Optional[str] = None,
		credentials_path: Optional[str] = None,
		credentials_b64: Optional[str] = None,
		scopes: Optional[Sequence[str]] = None,
	):
		self.spreadsheet_id = spreadsheet_id or os.getenv("SPREADSHEET_ID")
		if not self.spreadsheet_id:
			raise ValueError("Provide SPREADSHEET_ID to use SheetsClient")

		scopes = scopes or ["https://www.googleapis.com/auth/spreadsheets"]
		credentials = self._load_credentials(credentials_json, credentials_path, credentials_b64, scopes)
		self._service = build("sheets", "v4", credentials=credentials, cache_discovery=False)

	@staticmethod
	def _load_credentials(
		credentials_json: Optional[str],
		credentials_path: Optional[str],
		credentials_b64: Optional[str],
		scopes: Sequence[str],
	) -> Credentials:
		"""Return service-account credentials following the quickstart flow."""

		# Priority order: explicit JSON string, base64 blob, path, env fallbacks
		candidates = [credentials_json]

		if credentials_b64:
			decoded = base64.b64decode(credentials_b64).decode("utf-8")
			candidates.insert(0, decoded)

		if not any(candidates) and not credentials_path:
			credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or os.getenv("GOOGLE_SHEETS_CREDENTIALS_FILES")

		if credentials_path:
			return Credentials.from_service_account_file(credentials_path, scopes=scopes)

		for value in candidates:
			if value:
				data = json.loads(value)
				return Credentials.from_service_account_info(data, scopes=scopes)

		raise ValueError("Unable to locate Google Sheets credentials")

	def get_values(self, range_: str) -> List[List[str]]:
		"""Fetch values for ``range_`` (A1 notation)."""

		try:
			result = self._service.spreadsheets().values().get(
				spreadsheetId=self.spreadsheet_id,
				range=range_,
			).execute()
		except HttpError as exc:  # pragma: no cover
			raise RuntimeError(f"Sheets API error fetching values: {exc}") from exc

		return result.get("values", [])

	def update_values(
		self,
		range_: str,
		values: Iterable[Iterable],
		*,
		input_option: str = "USER_ENTERED",
	) -> Dict:
		"""Replace the contents of ``range_``."""

		body = {"values": [list(row) for row in values]}
		try:
			response = self._service.spreadsheets().values().update(
				spreadsheetId=self.spreadsheet_id,
				range=range_,
				body=body,
				valueInputOption=input_option,
			).execute()
		except HttpError as exc:  # pragma: no cover
			raise RuntimeError(f"Sheets API error updating values: {exc}") from exc

		return response

	def append_rows(
		self,
		range_: str,
		rows: Iterable[Iterable],
		*,
		input_option: str = "USER_ENTERED",
		insert_data_option: str = "INSERT_ROWS",
	) -> Dict:
		"""Append rows to the sheet."""

		body = {"values": [list(row) for row in rows]}
		try:
			response = self._service.spreadsheets().values().append(
				spreadsheetId=self.spreadsheet_id,
				range=range_,
				body=body,
				valueInputOption=input_option,
				insertDataOption=insert_data_option,
			).execute()
		except HttpError as exc:  # pragma: no cover
			raise RuntimeError(f"Sheets API error appending rows: {exc}") from exc

		return response

	def clear_range(self, range_: str) -> Dict:
		"""Clear values within ``range_`` while keeping formatting intact."""

		try:
			response = self._service.spreadsheets().values().clear(
				spreadsheetId=self.spreadsheet_id,
				range=range_,
				body={},
			).execute()
		except HttpError as exc:  # pragma: no cover
			raise RuntimeError(f"Sheets API error clearing range: {exc}") from exc

		return response


__all__ = ["SheetsClient"]
