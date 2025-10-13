
"""Google Sheets helper built on top of the official API quickstart.

See https://developers.google.com/workspace/sheets/api/quickstart/python for
the reference implementation that inspired this module.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any, Dict, Iterable, List, Optional, Sequence

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

	def get_available_sheets(self) -> List[str]:
		"""Get list of sheet names."""
		try:
			result = self._service.spreadsheets().get(spreadsheetId=self.spreadsheet_id).execute()
			return [sheet['properties']['title'] for sheet in result.get('sheets', [])]
		except HttpError as exc:
			raise RuntimeError(f"Sheets API error getting sheets: {exc}") from exc

	def create_sheet_if_not_exists(self, sheet_name: str) -> bool:
		"""Create sheet if it doesn't exist."""
		try:
			# Check if sheet already exists
			available_sheets = self.get_available_sheets()
			if sheet_name in available_sheets:
				return True

			# Create new sheet
			requests = [{
				'addSheet': {
					'properties': {
						'title': sheet_name
					}
				}
			}]

			self._service.spreadsheets().batchUpdate(
				spreadsheetId=self.spreadsheet_id,
				body={'requests': requests}
			).execute()

			return True

		except HttpError as exc:
			raise RuntimeError(f"Sheets API error creating sheet: {exc}") from exc

	def prepend_row(self, data: Dict[str, Any], sheet_name: str) -> bool:
		"""Prepend a row with the given data dict."""
		try:
			# Convert dict to list in the expected order
			row_values = [
				data.get('from', ''),
				data.get('type', ''),
				'',  # Number of Feedback
				data.get('product', ''),
				data.get('role', ''),
				data.get('fitur', ''),
				data.get('reporter', ''),
				data.get('reporting_date_time', ''),
				data.get('response_time', ''),
				'',  # Resolution Time
				'',  # Deployment Time
				'',  # Response Time (Days) SLA
				'',  # Resolution Time (Days) SLA
				'',  # Resolve Time (Days) SLA
				'',  # SLA Status Record
				data.get('responder', ''),
				data.get('description', ''),
				'',  # Step Reproduce
				data.get('severity', ''),
				data.get('urgency', ''),
				'',  # SLA
				'',  # Assignee
				'',  # Status
				'',  # Scheduled Release On
				data.get('link', ''),
				''   # Related Ticket
			]

			# Insert a new row at position 2 (after header)
			requests = [{
				"insertDimension": {
					"range": {
						"sheetId": self._get_sheet_id(sheet_name),
						"dimension": "ROWS",
						"startIndex": 1,
						"endIndex": 2
					},
					"inheritFromBefore": False
				}
			}]

			self._service.spreadsheets().batchUpdate(
				spreadsheetId=self.spreadsheet_id,
				body={"requests": requests}
			).execute()

			# Update the new row with data
			self.update_values(f"{sheet_name}!A2", [row_values])

			return True

		except HttpError as exc:
			raise RuntimeError(f"Sheets API error prepending row: {exc}") from exc

	def _get_sheet_id(self, sheet_name: str) -> int:
		"""Get the sheet ID for the given sheet name."""
		try:
			result = self._service.spreadsheets().get(spreadsheetId=self.spreadsheet_id).execute()
			for sheet in result.get('sheets', []):
				if sheet['properties']['title'] == sheet_name:
					return sheet['properties']['sheetId']
			raise ValueError(f"Sheet '{sheet_name}' not found")
		except HttpError as exc:
			raise RuntimeError(f"Sheets API error getting sheet ID: {exc}") from exc

	def get_all_links(self, sheet_name: str) -> List[str]:
		"""Get all links from column I (assuming links are in column I)."""
		range_ = f"{sheet_name}!I:I"
		values = self.get_values(range_)
		return [row[0] if row else '' for row in values]

	def get_all_codes(self, sheet_name: str) -> List[str]:
		"""Get all codes from column C (assuming codes are in column C)."""
		range_ = f"{sheet_name}!C:C"
		values = self.get_values(range_)
		return [row[0] if row else '' for row in values]


__all__ = ["SheetsClient"]
