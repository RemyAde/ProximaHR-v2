from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from db import companies_collection, employees_collection, leaves_collection
from models.employees import Employee
from models.leaves import Leave
from schemas.leave import CreateLeave
from utils import get_current_user

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

    leave_dict = leave_request.model_dump(exclude_unset=True)
    leave_dict["company_id"] = user["company_id"]
    leave_dict["employee_id"] = user["employee_id"]

    # Convert dates to datetime objects
    leave_dict["start_date"] = datetime.combine(leave_request.start_date, datetime.min.time())
    leave_dict["end_date"] = datetime.combine(leave_request.end_date, datetime.min.time())

    # Validate leave duration
    leave_duration = (leave_dict["end_date"] - leave_dict["start_date"]).days + 1  # Inclusive of start date
    if leave_duration <= 0:
        raise HTTPException(status_code=400, detail="End date must be after the start date")

    # Ensure leave is not requested for past dates
    if leave_dict["start_date"] < datetime.now(UTC):
        raise HTTPException(status_code=400, detail="Leave cannot be requested for past dates")

    leave_dict["duration"] = leave_duration

    # Check for overlapping leaves
    overlapping_leaves = await leaves_collection.find_one({
        "employee_id": user["employee_id"],
        "status": {"$in": ["pending", "approved"]},
        "$or": [
            {"start_date": {"$lte": leave_dict["end_date"]}, "end_date": {"$gte": leave_dict["start_date"]}},
            {"start_date": {"$gte": leave_dict["start_date"]}, "end_date": {"$lte": leave_dict["end_date"]}},
        ]
    })

    if overlapping_leaves:
        raise HTTPException(status_code=400, detail="You already have a pending or approved leave within this date range")

    # Save leave to the database
    leave_instance = Leave(**leave_dict)
    result = await leaves_collection.insert_one(leave_instance.model_dump())

    return {"message": "Leave request created successfully", "leave_id": str(result.inserted_id)}