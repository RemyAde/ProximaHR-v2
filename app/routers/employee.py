from datetime import datetime, timezone
from typing import Optional
from bson import ObjectId
from fastapi import APIRouter, File, HTTPException, Depends, Request, UploadFile, status
from db import employees_collection, leaves_collection, admins_collection, departments_collection
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

    if user_type != "employee":
        raise HTTPException(status_code=403, detail="Only employees can access this endpoint")
    
    company_id = user.get("company_id")
    if not company_id:
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
async def upload_profile_image(request: Request, image_file: UploadFile = File(...), user_and_type: tuple = Depends(get_current_user)):
    """
    Upload a profile image for an employee.
    This async function handles the upload of a profile image for an employee, validates user permissions,
    and updates the employee's profile in the database with the new image URL.
    Args:
        request (Request): The FastAPI request object containing base URL information.
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

    if user_type != "employee":
        raise HTTPException(status_code=403, detail="Only employees can access this endpoint")
    
    company_id = user.get("company_id")
    if not company_id:
        raise HTTPException(status_code=403, detail="You are not authorized to access this page")

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
async def delete_profile_image(user_and_type: tuple = Depends(get_current_user)):
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

    if user_type != "employee":
        raise HTTPException(status_code=403, detail="Only employees can access this endpoint")
    
    company_id = user.get("company_id")
    if not company_id:
        raise HTTPException(status_code=403, detail="You are not authorized to access this page")
    
    result = await employees_collection.update_one(
        {"employee_id": user["employee_id"]},
        {"$set":
         {"profile_image": ""}}
         )

        #  implement logic to remove pix from server
    
    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Image file not deleted.")
        

@router.get("/profile")
async def get_employee_profile(user_and_type: tuple = Depends(get_current_user)):
    """
    Retrieves the profile information of the currently authenticated employee.
    Parameters:
    ----------
    user_and_type : tuple
        A tuple containing user information and user type, obtained from the authentication dependency.
    Returns:
    -------
    dict
        A dictionary containing the serialized employee data with sensitive fields excluded.
    Raises:
    ------
    HTTPException
        404 if the employee is not found in the database, or 500 if an unexpected error occurs.
    """
    try:
        user, user_type = user_and_type
        employee_id = user["employee_id"]
        company_id = user["company_id"]
        hod = None
    
        # Fetch employee from the database
        employee = await employees_collection.find_one(
            {"employee_id": employee_id, "company_id": company_id}
        )
        if not employee:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="Employee not found."
            )
        
        # Convert ObjectId to string if present
        if "_id" in employee:
            employee["_id"] = str(employee["_id"])

        # Handle department field - convert ID to name if necessary
        if "department" in employee and employee["department"]:
            try:
                if ObjectId.is_valid(employee["department"]):
                    # If it's an ID, look up the department name - you'll need to implement this
                    # based on your department collection structure
                    department_doc = await departments_collection.find_one({"_id": ObjectId(employee["department"])})
                    if department_doc:
                        employee["department"] = department_doc.get("name", "")
                        hod = department_doc.get("hod", "")
                        if hod:
                            hod_doc = await employees_collection.find_one({"employee_id": hod})
                            if hod_doc:
                                hod = f"{hod_doc.get('first_name', '')} {hod_doc.get('last_name', '')}"
                            else:
                                hod = None
            except:
                # Keep existing department value if conversion fails
                pass
    
        if "current_year" in employee and isinstance(employee["current_year"], int):
            employee["current_year"] = str(employee["current_year"])
        
        # Create Employee instance and exclude sensitive fields
        serialized_employee = Employee(**employee).model_dump(
            exclude={
                "company_id",
                "password",
                "date_created",
                "_id",
                "gender",
                "country",
                "attendance",
                "position",
                "employment_status",
                "current_year",
                "payment_frequency",
                "used_leave_days",
                "carried_over_days",
                "account_name",
                "account_number",
                "bank_name",
                "payment_status",
            }
        )

        serialized_employee["hod"] = hod
    
        return {"data": serialized_employee}
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        raise HTTPException(status_code=400, detail=f"An error occurred while fetching the employee profile - {str(err)}")

    
@router.put("/update-profile") 
async def update_employee_profile(
    emergency_contact: Optional[dict] = {},
    email: Optional[str] = None,
    user_and_type: tuple = Depends(get_current_user)
    ):
    """
    Updates the employee profile with emergency contact and email information if provided.
    Args:
        emergency_contact (dict, optional): Emergency contact information.
        email (str, optional): Employee email address.
        user_and_type (tuple): Tuple containing user information and type from authentication.
    Returns:
        dict: A message confirming successful profile update.
    Raises:
        HTTPException: 404 if employee not found, 400 if update fails.
    """
    
    user, user_type = user_and_type
    employee_id = user["employee_id"]
    company_id = user["company_id"]
    
    employee = await employees_collection.find_one(
        {"employee_id": employee_id, "company_id": company_id}
    )   
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    update_fields = {}
    if emergency_contact is not None:
        update_fields["emergency_contact"] = emergency_contact
    if email is not None:
        update_fields["email"] = email
    if not update_fields:
        return {"message": "No fields to update"}
    
    result = await employees_collection.update_one(
        {"employee_id": employee_id, "company_id": company_id},
        {"$set": update_fields}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Profile update failed")
   
    return {"message": "Profile updated successfully"}


@router.get("/leave-statistics")
async def get_leave_statistics(user_and_type: tuple = Depends(get_current_user)):
    """
    Returns the count of pending leave requests, the number of annual leave days remaining,
    and the count of approved leave requests for the current employee.
    """
    user, user_type = user_and_type
    if user_type != "employee":
        raise HTTPException(status_code=403, detail="Only employees can access this endpoint")
    
    employee = await employees_collection.find_one({"_id": ObjectId(user.get("_id")), "company_id": user.get("company_id")})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    # Count pending leave requests
    pending_count = await leaves_collection.count_documents({
        "company_id": employee["company_id"],
        "employee_id": employee.get("employee_id"),
        "status": "pending"
    })
    
    # Count approved leaves
    approved_count = await leaves_collection.count_documents({
        "company_id": employee["company_id"],
        "employee_id": employee.get("employee_id"),
        "status": "approved"
    })
 
    remaining = employee.get("annual_leave_days", 0)
    
    return {
        "pending_leave_requests": pending_count,
        "approved_leave_requests": approved_count,
        "annual_leave_days_remaining": remaining
    }


@router.get("/leave-summary")
async def get_leave_cards(user_and_type: tuple = Depends(get_current_user)):
    """
    Retrieves a summary of leave information for the current employee, including:
    - Allocated annual leave days
    - Used leave days
    - Remaining leave days
    - Number of pending leave requests
    """
    user, user_type = user_and_type

    if user_type != "employee":
        raise HTTPException(status_code=403, detail="Only employees can access this endpoint")
    
    employee = await employees_collection.find_one({"employee_id": user.get("employee_id"), "company_id": user.get("company_id")})

    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    remaining_leave_days = employee.get("annual_leave_days", 0) # annual leave days decreases with approval
    used_leave_days = employee.get("used_leave_days", 0)
    allocated_leave_days = remaining_leave_days + used_leave_days
    pending_leaves_count = await leaves_collection.count_documents({
        "employee_id": user.get("employee_id"),
        "company_id": user.get("company_id"),
        "status": "pending"
    })

    return {
        "allocated_leave_days": allocated_leave_days,
        "used_leave_days": used_leave_days,
        "remaining_leave_days": remaining_leave_days,
        "pending_leaves": pending_leaves_count
    }


@router.get("/leaves")
async def get_employee_leaves(user_and_type: tuple = Depends(get_current_user)):
    """
    Retrieves all leave requests for the current employee, ordered by edited_at and created_at fields.
    Returns:
    -------
    List[Leave]
        A list of Leave objects representing the employee's leave requests.
    Raises:
    ------
    HTTPException
        - 403 if the user is not an employee.
        - 404 if the employee is not found.
    """
    user, user_type = user_and_type
    if user_type != "employee":
        raise HTTPException(status_code=403, detail="Only employees can access this endpoint")
    employee = await employees_collection.find_one({"employee_id": user.get("employee_id"), "company_id": user.get("company_id")})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    leaves = []
    async for leave in leaves_collection.find({"employee_id": user.get("employee_id"), "company_id": user.get("company_id")}).sort([("edited_at", -1), ("created_at", -1)]):
        leave["_id"] = str(leave["_id"])
        leaves.append(Leave(**leave))
    return leaves
