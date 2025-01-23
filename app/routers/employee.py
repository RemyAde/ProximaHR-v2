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
    """Create a new leave request for an employee.
    This function handles the creation of leave requests, including validation of dates,
    leave duration, and employee eligibility. It also sends notifications to company admins.
    Args:
        company_id (str): The ID of the company.
        leave_request (CreateLeave): The leave request details including start_date and end_date.
        user_and_type (tuple): Tuple containing user information and user type from authentication.
    Returns:
        dict: A dictionary containing:
            - message: Success message
            - leave_id: The ID of the created leave request
            - leave_days: Number of annual leave days available
    Raises:
        HTTPException: In the following cases:
            - 403: If user is not authorized for the company
            - 400: If end date is before start date
            - 400: If requested duration exceeds available leave days
            - 400: If leave is requested for past dates
            - 400: If there's an existing unresolved leave request
            - 400: If leave request creation fails
        UnknownEntityException: If employee is not found
    """
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
    """
    Upload a profile image for an employee.
    This async function handles the upload of a profile image for an employee, validates user permissions,
    and updates the employee's profile in the database with the new image URL.
    Args:
        request (Request): The FastAPI request object containing base URL information.
        company_id (str): The ID of the company the employee belongs to.
        image_file (UploadFile): The image file to be uploaded (passed as a File).
        user_and_type (tuple): A tuple containing user information and user type (from dependency injection).
    Returns:
        dict: A message confirming successful upload.
    Raises:
        HTTPException: 
            - 403: If the user is not authorized (company_id mismatch)
            - 400: If no image file is provided
            - 400: If the profile image update fails in the database
    Dependencies:
        - get_current_user: For user authentication and authorization
        - create_media_file: For handling the file upload process
    """

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
    """
    Deletes the profile image of an employee.
    This async function removes the profile image reference from the employee's document
    in the database. It requires company_id authentication and verifies user permissions.
    Args:
        company_id (str): The ID of the company the employee belongs to.
        user_and_type (tuple): A tuple containing user information and user type,
            obtained from the get_current_user dependency.
    Raises:
        HTTPException: 
            - 403 if user is not authorized (company_id mismatch)
            - 400 if image deletion was unsuccessful
    Returns:
        None
    Note:
        The actual image file removal from server storage is not yet implemented.
    """

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