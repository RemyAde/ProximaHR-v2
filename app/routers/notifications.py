from fastapi import APIRouter, Depends, HTTPException
from typing import List
from db import notifications_collection
from schemas.notification import NotificationResponse
from utils.app_utils import get_current_user

router = APIRouter()

@router.get("/notifications", response_model=List[NotificationResponse])
async def get_notifications(
    user_and_type: tuple = Depends(get_current_user),
    skip: int = 0,
    limit: int = 10
):
    user, _ = user_and_type
    
    notifications = await notifications_collection.find(
        {"recipient_id": user["employee_id"], "is_read": False}
    ).skip(skip).limit(limit).to_list(None)
    
    return notifications

@router.put("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    user_and_type: tuple = Depends(get_current_user)
):
    user, _ = user_and_type
    
    result = await notifications_collection.update_one(
        {"_id": notification_id, "recipient_id": user["employee_id"]},
        {"$set": {"is_read": True}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    return {"message": "Notification marked as read"}