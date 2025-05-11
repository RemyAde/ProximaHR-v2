from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import Optional
from bson import ObjectId
from db import leaves_collection, employees_collection
from schemas.notification import NotificationType
from schemas.leave import LeaveTypeSummary, LeavesCount, LeaveList
from utils.app_utils import get_current_user
from utils.notification_utils import create_leave_notification
from utils.activity_utils import log_admin_activity
from utils.leave_utils import get_leave_type_counts_for_year, get_monthly_leave_distribution
from db import departments_collection

UTC = timezone.utc

router = APIRouter()


@router.get("/health")
async def health_check():
    """
    Health check endpoint to verify if the service is running.
    Returns:
        dict: A simple message indicating the service is running.
    """
    return {"message": "Leave Management Service is running"}


@router.get("/leaves-count", response_model=LeavesCount)
async def get_leaves_count(
    user_and_type: tuple = Depends(get_current_user)
):
    """
    Get leave counts for a given company.
    This async function retrieves the total number of leaves and their statuses for a specific company.
    Args:
        user_and_type (tuple): Tuple containing user object and user type from authentication
    Returns:
        dict: A dictionary containing:
            - leave_count (int): Total number of leaves
            - pending_leave_count (int): Number of pending leaves
            - approved_leave_count (int): Number of approved leaves
            - rejected_leave_count (int): Number of rejected leaves
    Raises:
        HTTPException: 
            - 403: If user is not an admin
            - 401: If company_id doesn't match user's company
            - 400: For any other errors during execution
    """
    user, user_type = user_and_type

    if user_type != "admin":
        raise HTTPException(status_code=403, detail="You are not authorized to perform this function")

    company_id = str(user.get("company_id"))
    if not company_id:
        raise HTTPException(status_code=401, detail="Company ID not found in user data")

    try:
        leave_count = await leaves_collection.count_documents({"company_id": company_id})
        pending_leave_count = await leaves_collection.count_documents({"company_id": company_id, "status": "pending"})
        approved_leave_count = await leaves_collection.count_documents({"company_id": company_id, "status": "approved"})
        rejected_leave_count = await leaves_collection.count_documents({"company_id": company_id, "status": "rejected"})

        return {
            "leave_count": leave_count,
            "pending_leave_count": pending_leave_count,
            "approved_leave_count": approved_leave_count,
            "rejected_leave_count": rejected_leave_count,
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"An error occurred - {e}")
    

@router.get("/", status_code=status.HTTP_200_OK, response_model=LeaveList)
async def list_leaves(
    status: Optional[str] = Query(
        None, 
        description="Search by pending, approved, or rejected"
    ),
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(10, ge=1, le=100, description="Number of items to return"),
    user_and_type: tuple = Depends(get_current_user)
):
    """
    List all leaves for a given company with optional status filtering and pagination.
    This async function retrieves leave records from the database, including employee details
    for each leave request. Only admin users can access this endpoint.
    Args:
        status (Optional[str]): Filter leaves by status ('pending', 'approved', or 'rejected')
        skip (int): Number of records to skip for pagination (default: 0)
        limit (int): Maximum number of records to return (default: 10, max: 100)
        user_and_type (tuple): Tuple containing user object and user type from authentication
    Returns:
        dict: A dictionary containing:
            - leave_count (int): Total number of leaves
            - pending_leave_count (int): Number of pending leaves
            - approved_leave_count (int): Number of approved leaves
            - rejected_leave_count (int): Number of rejected leaves
            - leave_data (list): List of leave records with employee details
            - skip (int): Number of records skipped
            - limit (int): Number of records returned
    Raises:
        HTTPException: 
            - 403: If user is not an admin
            - 401: If company_id doesn't match user's company
            - 400: For any other errors during execution
    """
    user, user_type = user_and_type

    if user_type != "admin":
        raise HTTPException(status_code=403, detail="You are not authorized to perform this function")

    company_id = str(user.get("company_id"))
    if not company_id:
        raise HTTPException(status_code=401, detail="Company ID not found in user data")

    try:
        leave_data = []
        employee_details = {}

        # Build the filter for the query based on status
        query = {"company_id": company_id}
        if status:
            query["status"] = status

        # Query leaves collection with sorting and pagination
        leaves_cursor = leaves_collection.find(query).sort(
            [("created_at", -1), ("edited_at", -1)]
        ).skip(skip).limit(limit)

        async for leave in leaves_cursor:
            if leave.get("employee_id"):
                employee_filter = {"employee_id": leave["employee_id"]}
                employee = await employees_collection.find_one(employee_filter)
                if employee:
                    # Fetch department name if department is an ObjectId or id
                    department_name = None
                    department = employee.get("department")
                    if department:
                        # If department is an ObjectId or string id, fetch department name from departments_collection
                        department_doc = await departments_collection.find_one({"_id": department}) if isinstance(department, ObjectId) else await departments_collection.find_one({"_id": ObjectId(department)})
                        if department_doc:
                            department_name = department_doc.get("name", department)
                        else:
                            department_name = department  # fallback to id if not found
                    employee_details = {
                        "name": f"{employee.get('first_name')} {employee.get('last_name')}",
                        "department": department_name
                    }

            leave_data.append({
                "leave_id": str(leave.get("_id", "")),
                "leave_type": leave.get("leave_type", ""),
                "duration": leave.get("duration", ""),
                "start_date": leave.get("start_date", ""),
                "end_date": leave.get("end_date", ""),
                "status": leave.get("status", ""),
                "employee_details": employee_details,
            })

        return {
            "leave_data": leave_data,
            "skip": skip,
            "limit": limit,
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"An error occurred - {e}")
    

@router.post("/{leave_id}/approve")
async def approve_leave(leave_id: str, user_and_type: tuple = Depends(get_current_user)):
    """
    Approves a leave request and updates related records.
    This function handles the approval process of a leave request by an admin user. It performs
    several validations, updates the leave status, deducts leave days from the employee's balance,
    and creates a notification for the employee.
    Args:
        leave_id (str): The ID of the leave request to be approved.
        user_and_type (tuple): A tuple containing the current user's information and type, obtained from authentication.
    Returns:
        dict: A message confirming the leave approval.
    Raises:
        HTTPException: 
            - 403: If the user is not an admin or doesn't belong to the same company
            - 404: If the leave request or employee is not found
            - 400: If the leave has already been approved or rejected
    Example:
        >>> response = await approve_leave("5f7d3a2b8e9d4c1f2a3b4c5d", user_and_type)
        >>> print(response)
        {"message": "Leave approved and leave days deducted"}
    """

    user, user_type = user_and_type

    if user_type != "admin":
        raise HTTPException(status_code=403, detail="You are not authorized to perform this function")

    leave = await leaves_collection.find_one({"_id": ObjectId(leave_id)})
    if not leave:
        raise HTTPException(status_code=404, detail="Leave not found")
    
    if leave["company_id"] != user["company_id"]:
        raise HTTPException(status_code=403, detail="You are not authorized to perform this function")
    
    if leave["status"] == "approved":
        raise HTTPException(status_code=400, detail="Leave has already been approved")
    
    if leave["status"] == "rejected":
        raise HTTPException(status_code=400, detail="Leave has already been rejected")

    employee = await employees_collection.find_one({"employee_id": leave["employee_id"]})
    if not employee:
        raise HTTPException(status_code=404, detail="User not found")

    leave_duration = leave["duration"]

    # Deduct leave days
    await employees_collection.update_one(
        {"employee_id": leave["employee_id"]},
        {"$inc": {"used_leave_days": leave_duration, "annual_leave_days": -leave_duration}}
    )

    # Update leave status
    await leaves_collection.update_one(
        {"_id": ObjectId(leave_id)},
        {"$set": {"status": "approved", "edited_at": datetime.now(UTC)}}
    )

    # Prepare notification data
    leave_notification_data = {
        "_id": str(leave["_id"]),
        "employee_name": f"{employee['first_name']} {employee['last_name']}",
        "status": "approved"
    }

    # Create notification
    await create_leave_notification(
        leave_request=leave_notification_data,
        notification_type=NotificationType.LEAVE_APPROVED,
        recipient_id=employee["employee_id"],
        company_id=employee["company_id"]
    )

    await log_admin_activity(
        admin_id=str(user["_id"]),
        type="leave",
        action="approved",
        status="success"
    )

    return {"message": "Leave approved and leave days deducted"}


@router.post("/{leave_id}/reject", status_code=status.HTTP_200_OK)
async def reject_leave(leave_id: str, user_and_type: tuple = Depends(get_current_user)):
    """
    Reject a leave request for an employee.
    This async function handles the rejection of leave requests by admin users. It performs several
    checks to ensure the request is valid and updates the leave status to 'rejected' in the database.
    Args:
        leave_id (str): The unique identifier of the leave request to be rejected.
        user_and_type (tuple): A tuple containing user information and user type, obtained from dependency injection.
                              Format: (user_dict, user_type_str)
    Returns:
        dict: A message confirming successful rejection of the leave request.
            Format: {"message": "Leave was successfully rejected"}
    Raises:
        HTTPException: 
            - 403: If the user is not an admin
            - 404: If leave request or employee is not found
            - 403: If leave has already been approved or rejected
            - 400: If there's an error updating the leave status
            - 400: For any other unexpected errors during execution
    Dependencies:
        - MongoDB collections: leaves_collection, employees_collection
        - Authentication: get_current_user dependency
        - Notification system: create_leave_notification function
    """

    user, user_type = user_and_type

    # Ensure the user is an admin
    if user_type != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="You are not authorized to perform this function"
        )

    try:
        # Retrieve the company ID
        company_id = str(user.get("company_id"))  # Ensure this is the correct field

        # Fetch the leave document
        leave_obj = await leaves_collection.find_one({"_id": ObjectId(leave_id), "company_id": company_id})
        if not leave_obj:
            raise HTTPException(status_code=404, detail="Leave not found or not associated with your company")
        
        # Fetch the employee document
        employee = await employees_collection.find_one({"employee_id": leave_obj["employee_id"], "company_id": company_id}) 
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found")
        
        # Ensure the leave has not already been approved
        if str(leave_obj.get("status")) == "approved":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Leave has already been approved")
        
        if str(leave_obj.get("status")) == "rejected":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Leave has already been rejected")

        # Update the leave status to "rejected"
        updated_leave = await leaves_collection.update_one(
            {"_id": ObjectId(leave_id), "company_id": company_id},
            {"$set": {"status": "rejected", "edited_at": datetime.now(UTC)}}
        )

        if updated_leave.modified_count == 0:
            raise HTTPException(
                status_code=400,
                detail="Unable to approve the leave; it may have already been rejected"
            )
           
        # Prepare notification data
        leave_notification_data = {
            "_id": str(leave_obj["_id"]),
            "employee_name": f"{employee['first_name']} {employee['last_name']}",
            "status": "rejected"
            }

        # Create notification
        await create_leave_notification(
            leave_request=leave_notification_data,
            notification_type=NotificationType.LEAVE_REJECTED,
            recipient_id=employee["employee_id"],
            company_id=employee["company_id"]
            )
        
        await log_admin_activity(
            admin_id=str(user["_id"]),
            type="leave",
            action="rejected",
            status="success"
        )

        return {"message": "Leave was successfully rejected"}
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"An error occurred: {e}"
        )

@router.get("/leave-type-distribution", response_model=LeaveTypeSummary)
async def leave_type_distribution(
    year: Optional[int] = Query(datetime.now().year, description="Year to summarize (default: current year)"),
    user_and_type: tuple = Depends(get_current_user)
):
    """
    Returns the total amount of leaves taken for each leave type in the specified year for the admin's company.
    Only accessible by admin users.
    """
    user, user_type = user_and_type
    if user_type != "admin":
        raise HTTPException(status_code=403, detail="You are not authorized to perform this function")
    company_id = str(user["company_id"])
    if not company_id:
        raise HTTPException(status_code=401, detail="Company ID not found in user data")
    leave_type_counts = await get_leave_type_counts_for_year(company_id, year)
    return {"leave_type_counts": leave_type_counts, "year": year}


@router.get("/monthly-leave-distribution")
async def monthly_leave_distribution(user_and_type: tuple = Depends(get_current_user)):
    user, _ = user_and_type
    company_id = user["company_id"]

    distribution = await get_monthly_leave_distribution(company_id)

    return {"data": distribution}