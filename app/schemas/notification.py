from pydantic import BaseModel
from typing import Optional, Union, List
from datetime import datetime
from enum import Enum

class NotificationType(str, Enum):
    BIRTHDAY = "birthday"
    WORK_ANNIVERSARY = "work_anniversary"
    LEAVE_REQUEST = "leave_request"
    LEAVE_APPROVED = "leave_approved"
    LEAVE_REJECTED = "leave_rejected"

class NotificationCreate(BaseModel):
    recipient_id: Union[str, List[str]]
    type: NotificationType
    message: str
    related_id: Optional[str]
    company_id: str
    is_read: bool = False

class NotificationResponse(NotificationCreate):
    id: str
    created_at: datetime