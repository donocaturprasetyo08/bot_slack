"""Configuration management using Pydantic BaseSettings."""

from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Config(BaseSettings):
    """Application configuration loaded from environment variables."""

    # Slack Configuration
    slack_bot_token: str = Field(..., env="SLACK_BOT_TOKEN")
    slack_user_token: Optional[str] = Field(default=None, env="SLACK_USER_TOKEN")
    slack_signing_secret: Optional[str] = Field(
        default=None, env="SLACK_SIGNING_SECRET"
    )
    user_id_slack_bot: Optional[str] = Field(default=None, env="USER_ID_SLACK_BOT")

    # LLM Configuration
    llm_api_key: Optional[str] = Field(
        default=None, env=["LLM_API_KEY", "GEMINI_API_KEY"]
    )
    llm_model: str = Field(default="gemini-2.5-flash", env="LLM_MODEL")

    # Google Sheets Configuration
    spreadsheet_id: str = Field(..., env="SPREADSHEET_ID")
    spreadsheet_id_bug: str = Field(..., env="SPREADSHEET_ID_BUG")
    google_credentials_b64: Optional[str] = Field(
        default=None, env="GOOGLE_CREDENTIALS_B64"
    )
    google_sheets_credentials_b64: Optional[str] = Field(
        default=None, env="GOOGLE_SHEETS_CREDENTIALS_B64"
    )

    # Slack List Configuration
    slack_list_team_id: Optional[str] = Field(default=None, env="SLACK_LIST_TEAM_ID")
    slack_list_id: Optional[str] = Field(default=None, env="SLACK_LIST_ID")
    slack_list_link_display_name: str = Field(
        default="Slack Thread", env="SLACK_LIST_LINK_DISPLAY_NAME"
    )
    slack_list_pqf_status_name: str = Field(
        default="New", env="SLACK_LIST_PQF_STATUS_NAME"
    )
    slack_list_default_name: str = Field(
        default="Delivery", env="SLACK_LIST_DEFAULT_NAME"
    )

    # Channel Configuration
    allowed_channels: str = Field(default="", env="ALLOWED_CHANNELS")
    forward_channel_id: str = Field(default="", env="FORWARD_CHANNEL_ID")

    # Bug Tracking Configuration
    bug_sheet_name: str = Field(default="Bug List", env="BUG_SHEET_NAME")

    # Application Configuration
    thread_pool_max_workers: int = Field(default=4, env="THREAD_POOL_MAX_WORKERS")
    port: int = Field(default=8080, env="PORT")

    class Config:
        env_file = ".env"
        case_sensitive = False

    @field_validator("allowed_channels", "forward_channel_id", mode="before")
    @classmethod
    def handle_empty_string(cls, v: Optional[str]) -> str:
        """Handle empty strings."""
        return v or ""

    @property
    def allowed_channels_list(self) -> List[str]:
        """Get allowed channels as list."""
        if self.allowed_channels:
            return [
                item.strip()
                for item in self.allowed_channels.split(",")
                if item.strip()
            ]
        return []

    @property
    def forward_channel_id_list(self) -> List[str]:
        """Get forward channel IDs as list."""
        if self.forward_channel_id:
            return [
                item.strip()
                for item in self.forward_channel_id.split(",")
                if item.strip()
            ]
        return []


# Global config instance
config = Config()
