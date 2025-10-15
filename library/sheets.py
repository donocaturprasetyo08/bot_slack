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
        credentials = self._load_credentials(
            credentials_json, credentials_path, credentials_b64, scopes
        )
        self._service = build(
            "sheets", "v4", credentials=credentials, cache_discovery=False
        )

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
            credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or os.getenv(
                "GOOGLE_SHEETS_CREDENTIALS_FILES"
            )

        if credentials_path:
            return Credentials.from_service_account_file(
                credentials_path, scopes=scopes
            )

        for value in candidates:
            if value:
                data = json.loads(value)
                return Credentials.from_service_account_info(data, scopes=scopes)

        raise ValueError("Unable to locate Google Sheets credentials")

    def get_values(self, range_: str) -> List[List[str]]:
        """Fetch values for ``range_`` (A1 notation)."""

        try:
            result = (
                self._service.spreadsheets()
                .values()
                .get(
                    spreadsheetId=self.spreadsheet_id,
                    range=range_,
                )
                .execute()
            )
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
            response = (
                self._service.spreadsheets()
                .values()
                .update(
                    spreadsheetId=self.spreadsheet_id,
                    range=range_,
                    body=body,
                    valueInputOption=input_option,
                )
                .execute()
            )
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
            response = (
                self._service.spreadsheets()
                .values()
                .append(
                    spreadsheetId=self.spreadsheet_id,
                    range=range_,
                    body=body,
                    valueInputOption=input_option,
                    insertDataOption=insert_data_option,
                )
                .execute()
            )
        except HttpError as exc:  # pragma: no cover
            raise RuntimeError(f"Sheets API error appending rows: {exc}") from exc

        return response

    def get_available_sheets(self) -> List[str]:
        """Get list of sheet names."""
        try:
            result = (
                self._service.spreadsheets()
                .get(spreadsheetId=self.spreadsheet_id)
                .execute()
            )
            return [sheet["properties"]["title"] for sheet in result.get("sheets", [])]
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
            requests = [{"addSheet": {"properties": {"title": sheet_name}}}]

            self._service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id, body={"requests": requests}
            ).execute()

            return True

        except HttpError as exc:
            raise RuntimeError(f"Sheets API error creating sheet: {exc}") from exc

    def prepend_row(
        self, data: Dict[str, Any], sheet_name: str, sheet_type: str = "main"
    ) -> bool:
        """Prepend a row with the given data dict. Supports different sheet types."""
        try:
            if sheet_type == "main":
                return self._prepend_main_row(data, sheet_name)
            elif sheet_type == "bug":
                return self._prepend_bug_row(data, sheet_name)
            else:
                raise ValueError(f"Unsupported sheet_type: {sheet_type}")

        except HttpError as exc:
            raise RuntimeError(f"Sheets API error prepending row: {exc}") from exc

    def _prepend_main_row(self, data: Dict[str, Any], sheet_name: str) -> bool:
        """Prepend a row for main sheets with SLA formulas."""
        # Formulas for SLA calculations (row 2)
        row_num = 2
        response_time_sla_formula = f'=IF(ISBLANK(I{row_num}), "Waiting Response", IF(H{row_num} = I{row_num}, 1, NETWORKDAYS(H{row_num}, I{row_num}) - 1))'
        resolution_time_sla_formula = f'=IF(ISBLANK(J{row_num}), "Waiting Solution", IF(H{row_num} = J{row_num}, 1, NETWORKDAYS(H{row_num}, J{row_num}) - 1))'
        resolve_time_sla_formula = f'=IF(AND(ISBLANK(J{row_num}), ISBLANK(K{row_num})), "Waiting Solution", IF(ISBLANK(K{row_num}), "Feedback on progress", IF(H{row_num} = K{row_num}, 1, NETWORKDAYS(H{row_num}, K{row_num}) - 1)))'
        sla_status_record_formula = f'=IFS(AND(ISBLANK(J{row_num}), ISBLANK(K{row_num})), "Waiting Solution", ISBLANK(K{row_num}), "Feedback on progress", N{row_num} <= U{row_num}, "MEET SLA", N{row_num} > U{row_num}, "OVER SLA")'
        sla_formula = f'=IF(T{row_num}="High",3,IF(T{row_num}="Medium",13,IF(T{row_num}="Low",30,"FALSE")))'

        # Convert dict to list in the expected order with formulas
        row_values = [
            data.get("from", ""),
            data.get("type", ""),
            "",  # Number of Feedback
            data.get("product", ""),
            data.get("role", ""),
            data.get("fitur", ""),
            data.get("reporter", ""),
            data.get("reporting_date_time", ""),
            data.get("response_time", ""),
            "",  # Resolution Time
            "",  # Deployment Time
            response_time_sla_formula,  # Response Time (Days) SLA
            resolution_time_sla_formula,  # Resolution Time (Days) SLA
            resolve_time_sla_formula,  # Resolve Time (Days) SLA
            sla_status_record_formula,  # SLA Status Record
            data.get("responder", ""),
            data.get("description", ""),
            "",  # Step Reproduce
            data.get("severity", ""),
            data.get("urgency", ""),
            sla_formula,  # SLA
            "",  # Assignee
            "",  # Status
            "",  # Scheduled Release On
            data.get("link", ""),
            "",  # Related Ticket
        ]

        # Insert a new row at position 2 (after header)
        requests = [
            {
                "insertDimension": {
                    "range": {
                        "sheetId": self._get_sheet_id(sheet_name),
                        "dimension": "ROWS",
                        "startIndex": 1,
                        "endIndex": 2,
                    },
                    "inheritFromBefore": False,
                }
            }
        ]

        self._service.spreadsheets().batchUpdate(
            spreadsheetId=self.spreadsheet_id, body={"requests": requests}
        ).execute()

        # Update the new row with data
        self.update_values(f"{sheet_name}!A2", [row_values])

        return True

    def _prepend_bug_row(self, data: Dict[str, Any], sheet_name: str) -> bool:
        """Prepend a row for bug sheets without formulas."""
        # Convert dict to list for bug tracking (no formulas needed)
        row_values = [
            data.get("from", ""),
            data.get("type", ""),
            data.get("code", ""),  # Code column for bug tracking
            data.get("product", ""),
            data.get("role", ""),
            data.get("fitur", ""),
            data.get("reporter", ""),
            data.get("reporting_date_time", ""),
            data.get("deskripsi", ""),  # Description for bugs
            "",  # Step Reproduce
            data.get("severity", ""),
            data.get("urgency", ""),
            "",  # Assignee
            "",  # Status
            "",  # Scheduled Release On
            data.get("link", ""),
            "",  # Note
        ]

        # Insert a new row at position 2 (after header)
        requests = [
            {
                "insertDimension": {
                    "range": {
                        "sheetId": self._get_sheet_id(sheet_name),
                        "dimension": "ROWS",
                        "startIndex": 1,
                        "endIndex": 2,
                    },
                    "inheritFromBefore": False,
                }
            }
        ]

        self._service.spreadsheets().batchUpdate(
            spreadsheetId=self.spreadsheet_id, body={"requests": requests}
        ).execute()

        # Update the new row with data
        self.update_values(f"{sheet_name}!A2", [row_values])

        return True

    def _get_sheet_id(self, sheet_name: str) -> int:
        """Get the sheet ID for the given sheet name."""
        try:
            result = (
                self._service.spreadsheets()
                .get(spreadsheetId=self.spreadsheet_id)
                .execute()
            )
            for sheet in result.get("sheets", []):
                if sheet["properties"]["title"] == sheet_name:
                    return sheet["properties"]["sheetId"]
            raise ValueError(f"Sheet '{sheet_name}' not found")
        except HttpError as exc:
            raise RuntimeError(f"Sheets API error getting sheet ID: {exc}") from exc

    def get_all_links(self, sheet_name: str) -> List[str]:
        """Get all links from column I (assuming links are in column I)."""
        range_ = f"{sheet_name}!I:I"
        values = self.get_values(range_)
        return [row[0] if row else "" for row in values]

    def get_all_codes(self, sheet_name: str) -> List[str]:
        """Get all codes from column C (assuming codes are in column C)."""
        range_ = f"{sheet_name}!C:C"
        values = self.get_values(range_)
        return [row[0] if row else "" for row in values]

    def update_column_by_link(
        self, sheet_name: str, link: str, column_name: str, value: str
    ) -> bool:
        """Update a specific column for the row where 'Link Message' matches link."""
        try:
            # Get all data to find the row with matching link
            all_data = self.get_all_data(sheet_name)
            if not all_data or len(all_data) < 2:
                return False

            header = all_data[0]
            try:
                link_idx = header.index("Link Message")
                col_idx = header.index(column_name)
            except ValueError:
                return False

            # Find the row with matching link
            clean_link = link.split("&cid=")[0] if link else link
            for i, row in enumerate(
                all_data[1:], start=2
            ):  # start=2 for 1-based row number
                if len(row) > link_idx:
                    row_link = row[link_idx].split("&cid=")[0] if row[link_idx] else ""
                    if row_link == clean_link:
                        cell = f"{self._get_column_letter(col_idx + 1)}{i}"
                        self.update_values(f"{sheet_name}!{cell}", [[value]])
                        return True
            return False
        except HttpError as exc:
            raise RuntimeError(f"Sheets API error updating column: {exc}") from exc

    def get_all_data(self, sheet_name: str) -> Optional[List[List[str]]]:
        """Get all data from the spreadsheet."""
        try:
            # Get headers first to determine column count
            headers = [
                "From",
                "Type",
                "Number of Feedback",
                "Product",
                "Role",
                "Modul/Fitur",
                "Reporter",
                "Reporting Date Time",
                "Response Time",
                "Resolution Time",
                "Deployment Time",
                "Response Time (Days) SLA",
                "Resolution Time (Days) SLA",
                "Resolve Time (Days) SLA",
                "SLA Status Record",
                "Responder",
                "Deskripsi",
                "Step Reproduce",
                "Severity",
                "Urgency",
                "SLA",
                "Assignee",
                "Status",
                "Scheduled Release On",
                "Link Message",
                "Related Ticket",
            ]
            num_cols = len(headers)
            last_col = self._get_column_letter(num_cols)
            data_range = f"A:{last_col}"
            result = (
                self._service.spreadsheets()
                .values()
                .get(
                    spreadsheetId=self.spreadsheet_id,
                    range=f"{sheet_name}!{data_range}",
                )
                .execute()
            )

            return result.get("values", [])

        except HttpError as exc:
            raise RuntimeError(f"Sheets API error getting data: {exc}") from exc

    @staticmethod
    def _get_column_letter(n: int) -> str:
        """Convert column number to letter (1 = A, 26 = Z, 27 = AA, etc.)."""
        result = ""
        while n > 0:
            n, remainder = divmod(n - 1, 26)
            result = chr(65 + remainder) + result
        return result


class SheetsClientFactory:
    """Factory for creating different types of SheetsClient instances."""

    @staticmethod
    def create_main_client() -> SheetsClient:
        """Create a SheetsClient for main spreadsheet operations."""
        return SheetsClient(
            credentials_b64=os.getenv("GOOGLE_SHEETS_CREDENTIALS_B64"),
            spreadsheet_id=os.getenv("SPREADSHEET_ID"),
        )

    @staticmethod
    def create_bug_client() -> SheetsClient:
        """Create a SheetsClient for bug tracking operations."""
        return SheetsClient(
            credentials_b64=os.getenv("GOOGLE_SHEETS_CREDENTIALS_B64"),
            spreadsheet_id=os.getenv("SPREADSHEET_ID_BUG"),
        )


__all__ = ["SheetsClient", "SheetsClientFactory"]
