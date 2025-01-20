from datetime import datetime
from pytz import UTC
from db import notifications_collection, employees_collection
from schemas.notification import NotificationCreate, NotificationType

async def create_notification(notification: NotificationCreate):
    return await notifications_collection.insert_one(notification.model_dump())

async def check_birthdays_and_anniversaries():
    today = datetime.now(UTC)
    
    # Find employees with birthdays today
    birthday_pipeline = [
        {
            "$match": {
                "$expr": {
                    "$and": [
                        {"$eq": [{"$dayOfMonth": "$date_of_birth"}, today.day]},
                        {"$eq": [{"$month": "$date_of_birth"}, today.month]}
                    ]
                }
            }
        }
    ]
    
    birthday_employees = await employees_collection.aggregate(birthday_pipeline).to_list(None)
    
    # Find work anniversaries
    anniversary_pipeline = [
        {
            "$match": {
                "$expr": {
                    "$and": [
                        {"$eq": [{"$dayOfMonth": "$employment_date"}, today.day]},
                        {"$eq": [{"$month": "$employment_date"}, today.month]},
                        {"$lt": ["$employment_date", today]}
                    ]
                }
            }
        }
    ]
    
    anniversary_employees = await employees_collection.aggregate(anniversary_pipeline).to_list(None)
    
    # Group employees by company
    company_employees = {}
    async for employee in employees_collection.find({}, {"employee_id": 1, "company_id": 1}):
        company_id = employee["company_id"]
        if company_id not in company_employees:
            company_employees[company_id] = []
        company_employees[company_id].append(employee["employee_id"])
    
    notifications = []
    
    for employee in birthday_employees:
        company_id = employee["company_id"]
        recipients = company_employees.get(company_id, [])
        if recipients:
            notifications.append(
                NotificationCreate(
                    recipient_id=recipients,
                    type=NotificationType.BIRTHDAY,
                    message=f"Today is {employee['first_name']} {employee['last_name']}'s birthday! 🎉",
                    related_id=employee['employee_id'],
                    company_id=company_id
                )
            )
    
    for employee in anniversary_employees:
        company_id = employee["company_id"]
        recipients = company_employees.get(company_id, [])
        years = today.year - employee['employment_date'].year
        if recipients:
            notifications.append(
                NotificationCreate(
                    recipient_id=recipients,
                    type=NotificationType.WORK_ANNIVERSARY,
                    message=f"Congratulations! {employee['first_name']} {employee['last_name']} completes {years} years with us today! 🎊",
                    related_id=employee['employee_id'],
                    company_id=company_id
                )
            )
    
    # Insert notifications
    if notifications:
        await notifications_collection.insert_many([n.dict() for n in notifications])

async def create_leave_notification(leave_request, notification_type, recipient_id, company_id):    
    message = {
        "leave_request": f"New leave request from {leave_request['employee_name']}",
        "leave_approved": f"Your leave request has been approved",
        "leave_rejected": f"Your leave request has been rejected"
    }
    
    notification = NotificationCreate(
        company_id=company_id,
        recipient_id=recipient_id,
        type=notification_type,
        message=message[notification_type],
        related_id=str(leave_request['_id'])
    )
    
    await create_notification(notification)