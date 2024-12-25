from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from db import employees_collection, timer_logs_collection, leaves_collection, payroll_collection
from utils import get_current_user
from report_analytics_utils import calculate_attendance_trend, calculate_leave_utilization_trend, calculate_payroll_trend

router = APIRouter()

@router.get("/attendance-rate")
async def get_attendance_rate(user_and_type: tuple = Depends(get_current_user)):
    user, user_type = user_and_type
    if user_type != "admin":
        raise HTTPException(status_code=403, detail="Only admins can access this data.")
    
    try:
        result = await calculate_attendance_trend(user["company_id"], employees_collection, timer_logs_collection)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/leave-utilization")
async def get_leave_utilization(user_and_type: tuple = Depends(get_current_user)):
    user, user_type = user_and_type
    if user_type != "admin":
        raise HTTPException(status_code=403, detail="Only admins can access this data.")
    
    try:
        result = await calculate_leave_utilization_trend(user["company_id"], employees_collection, leaves_collection)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    

@router.get("/payroll", response_model=dict)
async def get_payroll_cost_and_trend(user_and_type: tuple = Depends(get_current_user)):
    user, user_type = user_and_type
    if user_type != "admin":
        raise HTTPException(status_code=403, detail="Only admins can access this data.")
    
    company_id = user["company_id"]

    now = datetime.now(timezone.utc)
    current_year = now.year
    previous_year = current_year - 1

    try:
        # Get the current year's payroll cost
        payroll_cost_cursor = employees_collection.aggregate([
            {
                "$match": {
                    "company_id": company_id,
                    "employment_status": {"$ne": "inactive"}  # Exclude inactive employees
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total_payroll_cost": {
                        "$sum": {
                            "$add": [
                                "$base_salary",
                                {"$ifNull": ["$overtime_hours_allowance", 0]},
                                {"$ifNull": ["$housing_allowance", 0]},
                                {"$ifNull": ["$transport_allowance", 0]},
                                {"$ifNull": ["$medical_allowance", 0]},
                                {"$ifNull": ["$company_match", 0]}
                            ]
                        }
                    }
                }
            }
        ])

        payroll_cost_result = await payroll_cost_cursor.to_list(length=1)
        current_payroll = payroll_cost_result[0]["total_payroll_cost"] if payroll_cost_result else 0

        # Get the previous year's payroll cost
        previous_payroll_doc = await payroll_collection.find_one(
            {"company_id": company_id, "year": previous_year},
            {"total_payroll_cost": 1, "_id": 0}
        )

        previous_payroll = previous_payroll_doc["total_payroll_cost"] if previous_payroll_doc else 0

        # Calculate trend (default to 100 if previous payroll is unavailable)
        trend = await calculate_payroll_trend(current_payroll, previous_payroll)

        return {
            "company_id": company_id,
            "payroll_cost": current_payroll,
            "trend": trend
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving payroll data: {e}")