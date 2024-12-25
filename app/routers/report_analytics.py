from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
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
    

@router.get("/workforce", response_model=dict)
async def get_workforce_growth_and_trend(user_and_type: tuple = Depends(get_current_user)):
    user, user_type = user_and_type
    if user_type != "admin":
        raise HTTPException(status_code=403, detail="Only admins can access this data.")
    
    company_id = user["company_id"]

    now = datetime.now(timezone.utc)
    current_year = now.year
    previous_year = current_year - 1

    try:
        # Total active employees at the end of the current year
        current_workforce_cursor = employees_collection.aggregate([
            {
                "$match": {
                    "company_id": company_id,
                    "employment_status": {"$ne": "inactive"},  # Exclude inactive employees
                    "date_created": {
                        "$lte": datetime(current_year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)  # Employees created up to the end of the year
                    }
                }
            },
            {"$count": "count"}
        ])
        current_workforce_result = await current_workforce_cursor.to_list(length=1)
        current_workforce_count = current_workforce_result[0]["count"] if current_workforce_result else 0

        # Total active employees at the end of the previous year
        previous_workforce_cursor = employees_collection.aggregate([
            {
                "$match": {
                    "company_id": company_id,
                    "employment_status": {"$ne": "inactive"},  # Exclude inactive employees
                    "date_created": {
                        "$lte": datetime(previous_year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)  # Employees created up to the end of the previous year
                    }
                }
            },
            {"$count": "count"}
        ])
        previous_workforce_result = await previous_workforce_cursor.to_list(length=1)
        previous_workforce_count = previous_workforce_result[0]["count"] if previous_workforce_result else 0

        # Calculate workforce trend (growth or decline)
        if previous_workforce_count > 0:
            trend = ((current_workforce_count - previous_workforce_count) / previous_workforce_count) * 100
        else:
            trend = 100  # Default to 100% if no workforce existed in the previous year

        return {
            "company_id": company_id,
            "current_workforce": current_workforce_count,
            "previous_workforce": previous_workforce_count,
            "trend": trend
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving workforce data: {e}")
    

@router.get("/overtime-by-department", response_model=dict)
async def get_overtime_by_department(
    year: int = Query(None, description="Filter overtime hours for a specific year (e.g., 2024)"),
    user_and_type: tuple = Depends(get_current_user)
):
    """
    Calculate total overtime hours by department with an optional yearly filter.
    """
    user, user_type = user_and_type
    if user_type != "admin":
        raise HTTPException(status_code=403, detail="Only admins can access this data.")
    
    company_id = user.get("company_id")

    try:
        # Build the match filter
        match_filter = {
            "company_id": company_id,  # Filter by company
            "attendance": {"$exists": True, "$ne": []},  # Ensure attendance exists and is not empty
        }

        # Add a year filter if provided
        if year:
            start_of_year = datetime(year, 1, 1)
            end_of_year = datetime(year, 12, 31, 23, 59, 59)
            match_filter["attendance.date"] = {"$gte": start_of_year, "$lte": end_of_year}

        # MongoDB aggregation pipeline
        overtime_by_department = await employees_collection.aggregate([
            {"$match": match_filter},
            {"$unwind": "$attendance"},  # Flatten attendance array
            {
                "$match": {  # Ensure filtering within the specified year after unwinding
                    "attendance.date": {"$gte": start_of_year, "$lte": end_of_year}
                } if year else {}
            },
            {
                "$group": {
                    "_id": "$department",  # Group by department
                    "total_overtime_hours": {
                        "$sum": {
                            "$ifNull": ["$attendance.overtime_hours", 0]  # Sum overtime_hours, default to 0
                        }
                    }
                }
            },
            {"$sort": {"total_overtime_hours": -1}}  # Sort by overtime in descending order (optional)
        ]).to_list(length=None)

        # Format response
        result = {entry["_id"]: entry["total_overtime_hours"] for entry in overtime_by_department}

        return {
            "company_id": company_id,
            "overtime_by_department": result,
            "year": year
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calculating overtime by department: {e}")