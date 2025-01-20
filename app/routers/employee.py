from datetime import datetime, timezone
from fastapi import APIRouter, File, HTTPException, Depends, Request, UploadFile
from db import employees_collection, leaves_collection, admins_collection
from models.employees import Employee
from models.leaves import Leave
from schemas.leave import CreateLeave
from schemas.notification import NotificationType
from utils.app_utils import get_current_user
from utils.notification_utils import create_leave_notification
from utils.image_utils import create_media_file
from exceptions import get_unknown_entity_exception

UTC = timezone.utc

router = APIRouter()


@router.post("/leave/create")
async def create_leave(
    company_id: str, 
    leave_request: CreateLeave, 
    user_and_type: tuple = Depends(get_current_user)
):
    user, user_type = user_and_type

    if company_id != user.get("company_id"):
        raise HTTPException(status_code=403, detail="You are not authorized to access this page")

    employee = await employees_collection.find_one({"company_id": company_id, "employee_id": user.get("employee_id")})
    if not employee:
        raise get_unknown_entity_exception()
    leave_days = employee.get("annual_leave_days")

    leave_dict = leave_request.model_dump(exclude_unset=True)
    leave_dict["company_id"] = user["company_id"]
    leave_dict["employee_id"] = user["employee_id"]

    # Convert dates to datetime objects
    leave_dict["start_date"] = datetime.combine(leave_request.start_date, datetime.min.time(), UTC)
    leave_dict["end_date"] = datetime.combine(leave_request.end_date, datetime.min.time(), UTC)

    # Validate leave duration
    leave_duration = (leave_dict["end_date"] - leave_dict["start_date"]).days + 1  # Inclusive of start date
    if leave_duration <= 0:
        raise HTTPException(status_code=400, detail="End date must be after the start date")

    if leave_duration > leave_days:
        raise HTTPException(status_code=400, detail="You do not have enough leave days left")

    # Ensure leave is not requested for past dates
    if leave_dict["start_date"] < datetime.now(UTC):
        raise HTTPException(status_code=400, detail="Leave cannot be requested for past dates")

    leave_dict["duration"] = leave_duration

    existing_leave = await leaves_collection.find_one({
        "employee_id": user["employee_id"],
        "status": {"$in": ["pending", "approved"]},
        "end_date": {"$gte": datetime.now(timezone.utc)}  # Ongoing approved leave
    })
    if existing_leave:
        raise HTTPException(status_code=400, detail="You cannot apply for leave until your current leave is resolved or ends")

    # Save leave to the database
    leave_instance = Leave(**leave_dict)
    result = await leaves_collection.insert_one(leave_instance.model_dump())
    
    if result.inserted_id is None:
        raise HTTPException(status_code=400, detail="Leave request not created")
    
    leave_notification_data = {}
    if result.inserted_id:
        company_admin = await admins_collection.find_one({"company_id": company_id, "role": "admin"})

        leave_notification_data = {
            "_id": str(result.inserted_id),
            "employee_name": f"{employee.get('first_name')} {employee.get('last_name')}",
            "status": "pending"
        }

    await create_leave_notification(
        company_id=company_id,
        recipient_id=company_admin.get("email"),
        notification_type=NotificationType.LEAVE_REQUEST,
        leave_request=leave_notification_data)
    
    return {"message": "Leave request created successfully", "leave_id": str(result.inserted_id), "leave_days": leave_days}


@router.post("/profile-image-upload")
async def upload_profile_image(request: Request, company_id: str, image_file: UploadFile = File(...), user_and_type: tuple = Depends(get_current_user)):
    user, user_type = user_and_type

    if company_id != user.get("company_id"):
        raise HTTPException(status_code=403, detail="You are not authorized to perform this function")

    if not image_file:
        raise HTTPException(status_code=400, detail="You must upload an image file")
    
    media_token_name = await create_media_file(type=user_type, file=image_file)

    result = await employees_collection.update_one(
        {"employee_id": user["employee_id"]}, 
        {"$set": 
         {"profile_image": f"{request.base_url}static/uploads/employee/{media_token_name}"}}
        )

    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Profile image not uploaded")

    return {"message": "Profile image uploaded successfully"}


@router.delete("/delete-profile-image")
async def delete_profile_image(company_id: str, user_and_type: tuple = Depends(get_current_user)):
    user, user_type = user_and_type

    if company_id != user["company_id"]:
        raise HTTPException(status_code=403, detail="You are not authorized to perform this action")
    
    result = await employees_collection.update_one(
        {"employee_id": user["employee_id"]},
        {"$set":
         {"profile_image": ""}}
         )

        #  implement logic to remove pix from server
    
    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Image file not deleted.")