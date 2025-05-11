from datetime import datetime, timezone
from pytz import UTC
from fastapi import APIRouter, Depends, HTTPException, Query
from db import employees_collection, timer_logs_collection, leaves_collection, payroll_collection, departments_collection
from utils.app_utils import get_current_user
from utils.report_analytics_utils import (calculate_attendance_trend, calculate_department_attendance_percentage, 
                                    calculate_leave_utilization_trend, calculate_payroll_trend, 
                                    serialize_objectid, calculate_company_monthly_attendance,
                                    calculate_overtime_for_department, calculate_attendance_for_department)

router = APIRouter()

@router.get("/attendance-rate")
async def get_attendance_rate(user_and_type: tuple = Depends(get_current_user)):
    """
    Retrieves attendance rate statistics for a company.
    This asynchronous function calculates and returns attendance trends for a company based on employee timer logs.
    Only users with admin privileges can access this data.
    Args:
        user_and_type (tuple): A tuple containing user information and user type, obtained from get_current_user dependency.
            First element is the user dict containing company_id and other user details.
            Second element is the user type string.
    Returns:
        dict: A dictionary containing attendance rate statistics and trends.
    Raises:
        HTTPException: 
            - 403 error if the user is not an admin
            - 400 error if there's an issue calculating the attendance trend
    """

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
    """
    Retrieve leave utilization trend for a company.
    This endpoint is restricted to admin users. It calculates and returns the leave utilization trend
    for the company associated with the current user.
    Args:
        user_and_type (tuple): A tuple containing the current user and their type, provided by the dependency injection.
    Returns:
        dict: A dictionary containing the leave utilization trend data.
    Raises:
        HTTPException: If the user is not an admin (status code 403).
        HTTPException: If there is a ValueError during the calculation (status code 400).
    """

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
    """
    Retrieve the payroll cost and trend for the current and previous year for a given company.
    Args:
        user_and_type (tuple): A tuple containing the current user and their type, 
                               obtained from the dependency injection of `get_current_user`.
    Returns:
        dict: A dictionary containing the following keys:
            - company_id (str): The ID of the company.
            - payroll_cost (float): The total payroll cost for the current year.
            - trend (float): The percentage change in payroll cost from the previous year to the current year.
    Raises:
        HTTPException: If the user is not an admin (status code 403).
        HTTPException: If there is an error retrieving payroll data (status code 500).
    """
    
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
    """
    Retrieve the workforce growth and trend for the current and previous year for a given company.
    Args:
        user_and_type (tuple): A tuple containing the current user and their type, 
                               obtained from the dependency injection of `get_current_user`.
    Returns:
        dict: A dictionary containing the following keys:
            - company_id (str): The ID of the company.
            - current_workforce (int): The total number of active employees at the end of the current year.
            - previous_workforce (int): The total number of active employees at the end of the previous year.
            - trend (float): The percentage growth or decline in the workforce from the previous year to the current year.
    Raises:
        HTTPException: If the user is not an admin (status code 403).
        HTTPException: If there is an error retrieving workforce data (status code 500).
    """

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


@router.get("/overtime-by-department-by-month", response_model=dict)
async def get_overtime_by_department(   
    year: int = Query(None, description="Filter overtime hours for a specific year (e.g., 2024)"),
    user_and_type: tuple = Depends(get_current_user)
):
    """
    This endpoint aggregates overtime hours across all employees within each department,
    providing a monthly breakdown for the specified year. If no year is specified,
    it returns data for all available years.
    Args:
        year (int, optional): The year to filter overtime data (e.g., 2024)
        user_and_type (tuple): Tuple containing user information and user type from authentication
    Returns:
        dict: A dictionary containing:
            - company_id: The ID of the company
            - overtime_by_department: Dictionary with departments as keys and monthly overtime as values
              where months are represented as integers (1-12)
            - year: The year for which data was filtered (if specified)
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
                    "_id": {
                        "department": "$department",
                        "month": {"$month": "$attendance.date"}
                    },
                    "total_overtime_hours": {
                        "$sum": {
                            "$ifNull": ["$attendance.overtime_hours", 0]
                        }
                    }
                }
            },
            {"$sort": {"_id.month": 1, "total_overtime_hours": -1}}  # Sort by month and overtime
        ]).to_list(length=None)

        # Format response with monthly breakdown
        result = {}
        for entry in overtime_by_department:
            department = entry["_id"]["department"] or "Unassigned"  # Handle null department
            month = entry["_id"]["month"]
            overtime = entry["total_overtime_hours"]
            
            if department not in result:
                result[department] = {i: 0 for i in range(1, 13)}  # Initialize all months with 0
            
            result[department][month] = overtime

        return {
            "company_id": company_id,
            "overtime_by_department": result,
            "year": year
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calculating overtime by department: {e}")


@router.get("/top-attendance", response_model=dict)
async def get_best_attendance_records(
    year: int = Query(None, description="Filter attendance records for a specific year (e.g., 2024)"),
    top_n: int = Query(10, description="Number of top employees to retrieve"),
    user_and_type: tuple = Depends(get_current_user)
):
    """
    Retrieve the employees with the best attendance records based on total hours worked or attendance days.
    """
    user, user_type = user_and_type
    if user_type != "admin":
        raise HTTPException(status_code=403, detail="Only admins can access this data.")
    company_id = user.get("company_id")

    try:
        # Build the match filter
        match_filter = {"company_id": company_id, "attendance": {"$exists": True, "$ne": []}}

        # Add a year filter if provided
        if year:
            start_of_year = datetime(year, 1, 1)
            end_of_year = datetime(year, 12, 31, 23, 59, 59)
            match_filter["attendance.date"] = {"$gte": start_of_year, "$lte": end_of_year}

        # MongoDB aggregation pipeline
        best_attendance = await employees_collection.aggregate([
        {"$match": match_filter},
        {"$unwind": "$attendance"},  # Flatten attendance array
        {
            "$group": {
                "_id": "$_id",  # Group by employee
                "first_name": {"$first": "$first_name"},  # Retrieve employee's first name
                "last_name": {"$first": "$last_name"},  # Retrieve employee's last name
                "department": {"$first": "$department"},  # Retrieve employee's department
                "total_hours_worked": {"$sum": "$attendance.hours_worked"},  # Total hours worked
                "total_days_attended": {"$sum": 1}  # Count total days attended
            }
        },
        {
            "$addFields": {
                "full_name": {"$concat": ["$first_name", " ", "$last_name"]}  # Combine first and last name
            }
        },
        {"$sort": {"total_hours_worked": -1}},  # Sort by total hours worked in descending order
        {"$limit": top_n}  # Limit to top N employees
        ]).to_list(length=None)

        serialize_objectid(best_attendance)

        return {
            "company_id": company_id,
            "best_attendance_records": best_attendance,
            "year": year if year else "all years",
            "top_n": top_n
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving attendance records: {e}")
    

@router.get("/attendance/current-month")
async def get_department_attendance_percentage(user_and_type: tuple = Depends(get_current_user)):
    """
    Retrieves the attendance percentage for all departments.
    This asynchronous function calculates and returns the attendance percentage
    for each department in the organization by delegating the computation to
    the calculate_department_attendance_percentage function.
    Returns
    -------
    dict
        A dictionary containing department-wise attendance percentages where:
        - keys: department names (str)
        - values: attendance percentage (float)
    Example
    -------
    {
        'HR': 95.5,
        'Engineering': 88.2,
        'Sales': 92.0
    }
    """

    user, user_type = user_and_type
    if user_type != "admin":
        raise HTTPException(status_code=403, detail="Only admins can access this data.")
    company_id = user["company_id"]

    return await calculate_department_attendance_percentage(company_id=company_id)

    
@router.get("/attendance/yearly-trend")
async def get_yearly_attendance_trend(user_and_type: tuple = Depends(get_current_user)):
    """
    Fetch the monthly attendance percentage trend for the current year.
    """
    user, user_type = user_and_type
    if user_type != "admin":
        raise HTTPException(status_code=403, detail="Only admins can access this data.")
    company_id = user["company_id"]

    return await calculate_company_monthly_attendance(company_id=company_id)


@router.get("/overtime/by-department")
async def get_overtime_statistics_by_department(
    month: int = Query(..., ge=1, le=12, description="Month value (1-12)"),
    year: int = Query(datetime.now().year, description="Year value (default: current year)"),
    user_and_type: tuple = Depends(get_current_user)
):
    """
    Endpoint to get overtime statistics by department for the given month and year.
    """

    user, user_type = user_and_type
    if user_type != "admin":
        raise HTTPException(status_code=403, detail="Only admins can access this data.")
    company_id = user["company_id"]

    try:
        result = await calculate_overtime_for_department(month, year, company_id=company_id)
        if result:
            return {"data": result}
        # Return 404 when no overtime data is found
        return {"message": "No overtime data found for the given month and year", "data": []}
    except Exception as e:
        # Log the error for debugging (optional)
        print(f"Error occurred: {e}")
        raise HTTPException(status_code=500, detail="An error occurred while processing the request")
    

@router.get("/attendance/department-summary")
async def get_department_attendance_summary(
    month: int = Query(..., ge=1, le=12, description="Month value (1-12)"),
    year: int = Query(datetime.now().year, description="Year value (default: current year)"),
    user_and_type: tuple = Depends(get_current_user)
):
    """
    Endpoint to get attendance summary for each department.
    """
    user, user_type = user_and_type
    if user_type != "admin":
        raise HTTPException(status_code=403, detail="Only admins can access this data.")
    company_id = user["company_id"]

    try:
        # Get department summaries and attendance percentages
        result = await calculate_attendance_for_department(month=month, year=year, company_id=company_id)
        attendance_percentage = await calculate_department_attendance_percentage(company_id=company_id)

        # --- NEW: Fetch department id-name mapping ---
        dept_docs = await departments_collection.find({"company_id": company_id}).to_list(length=None)
        dept_id_to_name = {}
        for dept in dept_docs:
            # Support both ObjectId and string id
            dept_id_to_name[str(dept["_id"])] = dept.get("name", str(dept["_id"]))

        def get_dept_name(dept_key):
            # If it's already a name, return as is; if id, map to name
            return dept_id_to_name.get(str(dept_key), dept_key)

        # --- Remap result keys to department names ---
        remapped_result = {}
        for dept_key, summary in result.items():
            dept_name = get_dept_name(dept_key)
            remapped_result[dept_name] = summary

        # Remap attendance_percentage as well
        remapped_attendance_percentage = {}
        for dept_key, percent in attendance_percentage.items():
            dept_name = get_dept_name(dept_key)
            remapped_attendance_percentage[dept_name] = percent

        # Merge attendance_percentage into remapped_result
        for dept_name, summary in remapped_result.items():
            summary["attendance_percentage"] = remapped_attendance_percentage.get(dept_name, 0.0)

        if remapped_result:
            return {"data": remapped_result}

        return {"message": "No attendance data found for the given month and year", "data": []}

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=400, detail=f"An error occurred while processing the request - {e}")