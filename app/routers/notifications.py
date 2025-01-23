from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from pytz import UTC
from typing import List
from bson import ObjectId
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
    """
    Retrieves unread notifications for a user based on their type and ID.
    This asynchronous function fetches notifications from the database that match the following criteria:
    - Belong to the user's company
    - Are unread (is_read = False)
    - Are addressed to the user either directly or as part of a group
    Args:
        user_and_type (tuple): A tuple containing user information and user type from auth
        skip (int, optional): Number of records to skip for pagination. Defaults to 0
        limit (int, optional): Maximum number of records to return. Defaults to 10
    Returns:
        list: A list of notification dictionaries with the following transformations:
            - MongoDB _id field converted to string and renamed to id
            - created_at field added if missing (using current UTC time)
            - Other notification fields preserved as-is
    Example:
        >>> notifications = await get_notifications(user_and_type=('user@email.com', 'admin'))
        >>> print(notifications)
        [{'id': '507f1f77bcf86cd799439011', 'message': 'New notification', ...}]
    """
    
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
    """
    Mark a notification as read for the current user.
    Args:
        notification_id (str): The ID of the notification to mark as read
        user_and_type (tuple): Tuple containing user information and type (from dependency)
            - user (dict): User information containing either email (admin) or employee_id
            - user_type (str): Type of user ('admin' or 'employee')
    Returns:
        dict: A message confirming the notification was marked as read
    Raises:
        HTTPException: 404 if notification is not found for the given ID and recipient
    """
    user, user_type = user_and_type
    if user_type == "admin":
        recipient_id = user.get("email")
    else:
        recipient_id = user.get("employee_id")
    
    result = await notifications_collection.update_one(
        {"_id": ObjectId(notification_id), "recipient_id": recipient_id},
        {"$set": {"is_read": True}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    return {"message": "Notification marked as read"}