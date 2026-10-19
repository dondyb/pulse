from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CampaignIn(BaseModel):
    name: str = Field("", description="Internal campaign name")
    subject: str = ""
    body: str = Field("", description="Plain-text message body")
    audience: Literal["all_subscribers", "active_customers", "trial_users", "vip_customers"] = "all_subscribers"
    action: Literal["draft", "send", "schedule"] = Field("draft", description="Save as draft, send now, or schedule")
    scheduled_at: datetime | None = Field(None, description="ISO-8601 timestamp with offset; required for schedule")


class ContactIn(BaseModel):
    name: str = ""
    email: str = ""
    company: str = ""
    segment: Literal["active_customer", "trial_user", "vip_customer", "prospect"] = "prospect"
    subscribed: bool = True
