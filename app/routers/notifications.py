from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from pytz import UTC
from typing import List
from db import notifications_collection
from schemas.notification import NotificationResponse
from utils.app_utils import get_current_user

router = APIRouter()

@router.get("/", response_model=List[NotificationResponse])
async def get_notifications(
    user_and_type: tuple = Depends(get_current_user),
    skip: int = 0,
    limit: int = 10
):
    user, user_type = user_and_type
    company_id = user.get("company_id")
    
    if user_type == "admin":
        recipient_id = user.get("email")
    else:
        recipient_id = user.get("employee_id")

    query = {
        "company_id": company_id,
        "is_read": False,
        "$or": [
            {"recipient_id": recipient_id},
            {"recipient_id": {"$in": [recipient_id]}}
        ]
    }
    
    notifications = await notifications_collection.find(query)\
        .sort("created_at", -1)\
        .skip(skip)\
        .limit(limit)\
        .to_list(None)
    
    # Transform documents to match Pydantic model
    transformed_notifications = []
    for notification in notifications:
        notification["id"] = str(notification.pop("_id"))
        if "created_at" not in notification:
            notification["created_at"] = datetime.now(UTC)
        transformed_notifications.append(notification)
    
    return transformed_notifications

@router.put("/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    user_and_type: tuple = Depends(get_current_user)
):
    user, user_type = user_and_type
    if user_type == "admin":
        recipient_id = user.get("email")
    else:
        recipient_id = user.get("employee_id")
    
    result = await notifications_collection.update_one(
        {"_id": notification_id, "recipient_id": recipient_id},
        {"$set": {"is_read": True}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    return {"message": "Notification marked as read"}