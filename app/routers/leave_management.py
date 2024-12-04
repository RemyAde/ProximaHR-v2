from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field
from typing import List
from bson import ObjectId
from db import leaves_collection, companies_collection, employees_collection
from utils import get_current_user
from exceptions import get_user_exception, get_unknown_entity_exception


router = APIRouter(prefix="leaves", tags=["leaves"])


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
async def list_leaves(company_id: str, user_and_type: tuple = Depends(get_current_user)):
    user, user_type = user_and_type

    if user_type != "admin":
        raise HTTPException(status_code=403, detail="You are not authorized to perform this function")

    if company_id != user.get("company_id"):
        raise get_user_exception()

    try:
        leave_data = []
        employee_details = {}

        leave_count = 0
        pending_leave_count = 0
        approved_leave_count = 0
        rejected_leave_count = 0 

        leaves = leaves_collection.find({"company_id": company_id})

        async for leave in leaves:
            leave_count += 1

            if leave.get("employee_id"):
                employee_filter = {"employee_id": leave["employee_id"]}
                employee = await employees_collection.find_one(employee_filter)
                if employee:
                    employee_details = {
                        "name": f"{employee.get("first_name")} {employee.get("last_name")}",
                        "department": employee.get("department")
                    }
            
            if leave.get("status") == "pending":
                pending_leave_count += 1

            if leave.get("status") == "approved":
                approved_leave_count += 1

            if leave.get("status") == "rejected":
                rejected_leave_count += 1
            
            leave_data.append({
                "leave_id": str(leave.get("_id", "")),
                "leave_type": leave.get("leave_type", ""),
                "duration": leave.get("duration", ""),
                "start_date": leave.get("start_date", ""),
                "end_date": leave.get("end_date", ""),
                "status": leave.get("status", ""),
                "employee_details": employee_details
            })
        

        return {
            "leave_count": leave_count,
            "pending_leave_count": pending_leave_count,
            "approved_leave_count": approved_leave_count,
            "rejected_leave_count": rejected_leave_count,
            "leave_data": leave_data
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"An error has ocured - {e}")
    

@router.post("/{leave_id}/approve_leave", status_code=status.HTTP_200_OK)
async def approve_leave(leave_id: str, user_and_type: tuple = Depends(get_current_user)):
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
        
        if str(leave_obj.get("status")) == "approved":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Leave has already been approved")

        # Update the leave status to "approved"
        updated_leave = await leaves_collection.update_one(
            {"_id": ObjectId(leave_id), "company_id": company_id},
            {"$set": {"status": "approved"}}
        )

        if updated_leave.modified_count == 0:
            raise HTTPException(
                status_code=400,
                detail="Unable to approve the leave; it may have already been approved"
            )

        return {"message": "Leave was successfully approved"}
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"An error occurred: {e}"
        )


router.post("/{leave_id}/reject_leave", status_code=status.HTTP_200_OK)
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
            {"$set": {"status": "rejected"}}
        )

        if updated_leave.modified_count == 0:
            raise HTTPException(
                status_code=400,
                detail="Unable to approve the leave; it may have already been approved"
            )

        return {"message": "Leave was successfully approved"}
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"An error occurred: {e}"
        )