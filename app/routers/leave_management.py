from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, status, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from bson import ObjectId
from db import leaves_collection, employees_collection
from utils.app_utils import get_current_user
from exceptions import get_user_exception

UTC = timezone.utc

router = APIRouter()


class LeaveList(BaseModel):
    leave_count: int
    pending_leave_count: int
    approved_leave_count: int
    rejected_leave_count: int
    leave_data: List = Field(
        ...,
        description="list of dictionaries"
        )


@router.get("/", status_code=status.HTTP_200_OK, response_model=LeaveList)
async def list_leaves(
    company_id: str,
    status: Optional[str] = Query(
        None, 
        description="Search by pending, approved, or rejected"
    ),
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(10, ge=1, le=100, description="Number of items to return"),
    user_and_type: tuple = Depends(get_current_user)
):
    user, user_type = user_and_type

    if user_type != "admin":
        raise HTTPException(status_code=403, detail="You are not authorized to perform this function")

    if company_id != user.get("company_id"):
        raise get_user_exception()

    try:
        leave_data = []
        employee_details = {}

        # Always calculate total counts for all statuses
        leave_count = await leaves_collection.count_documents({"company_id": company_id})
        pending_leave_count = await leaves_collection.count_documents({"company_id": company_id, "status": "pending"})
        approved_leave_count = await leaves_collection.count_documents({"company_id": company_id, "status": "approved"})
        rejected_leave_count = await leaves_collection.count_documents({"company_id": company_id, "status": "rejected"})

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
                    employee_details = {
                        "name": f"{employee.get('first_name')} {employee.get('last_name')}",
                        "department": employee.get("department")
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
            "leave_count": leave_count,
            "pending_leave_count": pending_leave_count,
            "approved_leave_count": approved_leave_count,
            "rejected_leave_count": rejected_leave_count,
            "leave_data": leave_data,
            "skip": skip,
            "limit": limit,
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"An error occurred - {e}")
    

@router.post("/{leave_id}/approve")
async def approve_leave(leave_id: str, user_and_type: tuple = Depends(get_current_user)):
    user, user_type = user_and_type

    if user_type != "admin":
        raise HTTPException(status_code=403, detail="You are not authorized to perform this function")

    leave = await leaves_collection.find_one({"_id": ObjectId(leave_id)})
    if not leave:
        raise HTTPException(status_code=404, detail="Leave not found")

    user = await employees_collection.find_one({"employee_id": leave["employee_id"]})
    if not user:
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
        {"$set": {"status": "approved"}}
    )

    return {"message": "Leave approved and leave days deducted"}


@router.post("/{leave_id}/reject", status_code=status.HTTP_200_OK)
async def reject_leave(leave_id: str, user_and_type: tuple = Depends(get_current_user)):
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
        
        if str(leave_obj.get("status")) == "rejected":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Leave has already been rejected")

        # Update the leave status to "approved"
        updated_leave = await leaves_collection.update_one(
            {"_id": ObjectId(leave_id), "company_id": company_id},
            {"$set": {"status": "rejected", "edited_at": datetime.now(UTC)}}
        )

        if updated_leave.modified_count == 0:
            raise HTTPException(
                status_code=400,
                detail="Unable to approve the leave; it may have already been rejected"
            )

        return {"message": "Leave was successfully rejected"}
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"An error occurred: {e}"
        )