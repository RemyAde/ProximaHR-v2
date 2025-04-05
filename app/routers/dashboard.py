from datetime import datetime, timedelta
from pytz import UTC
from fastapi import APIRouter, HTTPException, Depends, status
from utils.report_analytics_utils import calculate_attendance_trend, calculate_average_working_hours
from db import companies_collection, employees_collection, departments_collection, leaves_collection, timer_logs_collection
from utils.app_utils import get_current_user
from exceptions import get_user_exception, get_unknown_entity_exception
from utils.dashboard_utils import get_upcoming_events_for_the_month
import calendar

router = APIRouter()


@router.get("/company-overview")
async def get_company_info(user_and_type: tuple = Depends(get_current_user)):
    """
    Get company overview information for a specific company.
    This endpoint retrieves key metrics and information about a company, including:
    - Total number of employees (staff size)
    - Number of departments
    - Number of pending leave requests
    - Overall attendance percentage\n
    Args:
        company_id: The registration number of the company
        user_and_type (tuple): Tuple containing user information and user type from authentication\n
    Returns:
        dict: A dictionary containing:
            - total_employees (int): Total number of employees in the company
            - department_count (int): Number of departments in the company
            - pending_leave_count (int): Number of pending leave requests
            - attendance_percentage (float): Overall attendance percentage\n
    Raises:
        HTTPException: 
            - 401 if user is not an admin
            - 401 if user doesn't belong to the requested company
            - 404 if company is not found
            - 400 for any other errors during processing
    """
    user, user_type = user_and_type
    if user_type != "admin":
        raise get_user_exception()
    
    company_id = user["company_id"]

    try:
        # Initialize with default values
        data = {
            "total_employees": 0,
            "department_count": 0,
            "pending_leave_count": 0,
            "attendance_percentage": 0.0
        }
        
        company = await companies_collection.find_one({"registration_number": company_id})
        if not company:
            return data
        
        if str(company.get("registration_number")) != str(user["company_id"]):
            raise get_user_exception()
    
        try:
            department_count = await departments_collection.count_documents({"company_id": company_id})
        except Exception:
            department_count = 0

        try:
            pending_leave_count = await leaves_collection.count_documents({"company_id": company_id, "status": "pending"})
        except Exception:
            pending_leave_count = 0

        try:
            attendance_percentage = await calculate_attendance_trend(user["company_id"], employees_collection, timer_logs_collection)
            attendance_percentage = round(attendance_percentage, 2) if attendance_percentage else 0.0
        except Exception:
            attendance_percentage = 0.0
        
        data.update({
            "total_employees": company.get("staff_size", 0),
            "department_count": department_count,
            "pending_leave_count": pending_leave_count,
            "attendance_percentage": attendance_percentage
        })

        return data

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"an error occurred - {e}")


@router.get("/department-overview")
async def department_overview(user_and_type: tuple = Depends(get_current_user)):
    """
    Retrieves an overview of department-related statistics for a specific company.
    This async function provides various metrics including department count, attendance rates,
    leave statistics, and average working hours. Only accessible to admin users.
    Args:
        company_id (str): The registration number of the company to get overview for.
        user_and_type (tuple): A tuple containing user information and user type, obtained from dependency injection.
                              Format: (user_dict, user_type_str)
    Returns:
        dict: A dictionary containing the following metrics:
            - department_count (int): Total number of departments in the company
            - attendance_rate (float): Average attendance rate as a percentage
            - approved_leave_count (int): Total number of approved leaves
            - active_leave_count (int): Number of currently active approved leaves
            - average_hours_worked (float): Average working hours per employee
    Raises:
        HTTPException: If there's an error processing the request (status code 400)
        UserException: If user is not an admin or doesn't belong to the specified company
    Note:
        - All numeric metrics default to 0 if there's an error calculating them
        - Attendance rate and average hours are rounded to 2 decimal places
    """

    user, user_type = user_and_type
    
    if user_type != "admin":
        raise get_user_exception()
    
    company_id = user["company_id"]
        
    try:
        data = {
            "department_count": 0,
            "attendance_rate": 0.0,
            "approved_leave_count": 0,
            "active_leave_count": 0,
            "average_hours_worked": 0.0
        }
        
        company = await companies_collection.find_one({"registration_number": company_id})
        if not company:
            return data
            
        if str(company.get("registration_number")) != str(user["company_id"]):
            raise get_user_exception()
            
        try:
            department_count = await departments_collection.count_documents({"company_id": company_id})
        except Exception:
            department_count = 0
            
        try:
            approved_leave_count = await leaves_collection.count_documents({
                "company_id": company_id,
                "status": "approved"
            })
        except Exception:
            approved_leave_count = 0
            
        try:
            active_leave_count = await leaves_collection.count_documents({
                "company_id": company_id,
                "status": "approved",
                "end_date": {"$gte": datetime.now(UTC)}
            })
        except Exception:
            active_leave_count = 0
            
        try:
            attendance_rate = await calculate_attendance_trend(company_id, employees_collection, timer_logs_collection)
            attendance_rate = round(attendance_rate, 2) if attendance_rate else 0.0
        except Exception:
            attendance_rate = 0.0
            
        try:
            avg_hours = await calculate_average_working_hours(company_id, timer_logs_collection)
            avg_hours = round(avg_hours, 2) if avg_hours else 0.0
        except Exception:
            avg_hours = 0.0
            
        data.update({
            "department_count": department_count,
            "attendance_rate": attendance_rate,
            "approved_leave_count": approved_leave_count,
            "active_leave_count": active_leave_count,
            "average_hours_worked": avg_hours
        })
        
        return data
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"an error occurred - {e}")

    
@router.get("/leave-overview")
async def leave_overview(user_and_type: tuple = Depends(get_current_user)):
    """
    Retrieves an overview of leave statistics for a specific company.
    This asynchronous function provides a summary of leave-related metrics including
    pending leaves, monthly approved leaves, and the overall leave approval rate.
    Only administrators have access to this information.
    Args:
        company_id (str): The registration number of the company
        user_and_type (tuple): A tuple containing user information and type, obtained from get_current_user dependency
    Returns:
        dict: A dictionary containing leave statistics with the following keys:
            - pending_leaves (int): Number of pending leave requests
            - monthly_approved_leaves (int): Number of approved leaves in the current month
            - leave_approval_rate (float): Percentage of approved leaves out of total leaves
    Raises:
        HTTPException: If there's an error processing the request or if database operations fail
        UserException: If the user is not an admin or doesn't belong to the specified company
    Notes:
        - The function performs multiple database queries to gather different metrics
        - Monthly approved leaves are calculated for the current calendar month
        - Leave approval rate is rounded to 2 decimal places
    """

    user, user_type = user_and_type
    
    if user_type != "admin":
        raise get_user_exception()
    
    company_id = user["company_id"]

    try:
        data = {
            "pending_leaves": 0,
            "monthly_approved_leaves": 0,
            "leave_approval_rate": 0.0
        }

        company = await companies_collection.find_one({"registration_number": company_id})
        if not company:
            return data
            
        if str(company.get("registration_number")) != str(user["company_id"]):
            raise get_user_exception()

        try:
            pending_count = await leaves_collection.count_documents({
                "company_id": company_id,
                "status": "pending"
            }) or 0
        except Exception:
            pending_count = 0

        try:
            current_month = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            next_month = (current_month.replace(day=28) + timedelta(days=4)).replace(day=1)
            monthly_approved = await leaves_collection.count_documents({
                "company_id": company_id,
                "status": "approved",
                "start_date": {"$gte": current_month, "$lt": next_month}
            }) or 0
        except Exception:
            monthly_approved = 0

        try:
            total_leaves = await leaves_collection.count_documents({"company_id": company_id}) or 0
            total_approved = await leaves_collection.count_documents({
                "company_id": company_id,
                "status": "approved"
            }) or 0
            approval_rate = round((total_approved / total_leaves * 100), 2) if total_leaves > 0 else 0.0
        except Exception:
            approval_rate = 0.0

        data.update({
            "pending_leaves": pending_count,
            "monthly_approved_leaves": monthly_approved,
            "leave_approval_rate": approval_rate
        })

        return data

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"an error occurred - {e}")
    

@router.get("/payroll-overview")
async def payroll_overview(user_and_type: tuple = Depends(get_current_user)):
    """
    Retrieve payroll overview statistics for a specific company.
    This async function provides key payroll metrics including total payroll costs,
    payment completion status, and next payroll date. Access is restricted to admin users
    who belong to the specified company.
    Args:
        company_id (str): The registration number of the company
        user_and_type (tuple): Tuple containing user information and type, obtained from get_current_user dependency
    Returns:
        dict: A dictionary containing the following payroll statistics:
            - total_payroll_cost (float): Sum of all active employees' compensation including base salary and allowances
            - paid_percentage (float): Percentage of active employees who have been paid
            - paid_employees (int): Number of active employees marked as paid
            - next_payroll_date (str): Next scheduled payroll date for the company
    Raises:
        HTTPException: If user is not authorized or if there's an error processing the request
        UserException: If user is not an admin or doesn't belong to the specified company
    Note:
        All monetary calculations are rounded to 2 decimal places.
        If no company is found, returns default values (zeros) for all metrics.
    """

    user, user_type = user_and_type
    
    if user_type != "admin":
        raise get_user_exception()
    
    company_id = user["company_id"]

    try:
        data = {
            "total_payroll_cost": 0.0,
            "paid_percentage": 0.0,
            "paid_employees": 0,
            "next_payroll_date": None
        }

        company = await companies_collection.find_one({"registration_number": company_id})
        if not company:
            return data
            
        if str(company.get("registration_number")) != str(user["company_id"]):
            raise get_user_exception()

        try:
            pipeline = [
                {
                    "$match": {
                        "company_id": company_id,
                        "employment_status": "active"
                    }
                },
                {
                    "$group": {
                        "_id": None,
                        "total_cost": {
                            "$sum": {
                                "$add": [
                                    {"$ifNull": ["$base_salary", 0]},
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
            ]
            result = await employees_collection.aggregate(pipeline).to_list(length=1)
            total_payroll = round(result[0]["total_cost"], 2) if result else 0.0
        except Exception:
            total_payroll = 0.0

        try:
            total_employees = await employees_collection.count_documents({
                "company_id": company_id,
                "employment_status": "active"
            }) or 0
            
            paid_employees = await employees_collection.count_documents({
                "company_id": company_id,
                "employment_status": "active",
                "payment_status": "paid"
            }) or 0
            
            paid_percentage = round((paid_employees / total_employees * 100), 2) if total_employees > 0 else 0.0
        except Exception:
            paid_employees = 0
            paid_percentage = 0.0

        now = datetime.now(UTC)
        last_day = calendar.monthrange(now.year, now.month)[1]
        last_date = datetime(now.year, now.month, last_day)
        
        # Adjust to the last weekday (Monday to Friday)
        while last_date.weekday() > 4:  # 4 is Friday, so anything greater is a weekend
            last_date -= timedelta(days=1)

        data.update({
            "total_payroll_cost": total_payroll,
            "paid_percentage": paid_percentage,
            "paid_employees": paid_employees,
            "next_payroll_date": last_date.isoformat()
        })

        return data

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"an error occurred - {e}")


@router.get("/events")
async def get_events(user_and_type: tuple = Depends(get_current_user)):
    """
    Retrieves upcoming birthdays and work anniversaries for employees in a given company.
    This async function fetches events (birthdays and work anniversaries) occurring in the next 30 days
    for active employees of a specified company. Only admin users can access this information.
    Args:
        company_id (str): The registration number of the company
        user_and_type (tuple): A tuple containing user information and user type, obtained from get_current_user dependency
    Returns:
        dict: A dictionary containing:
            - birthday_count (int): Number of upcoming birthdays
            - birthdays (list): List of employees with upcoming birthdays
            - anniversary_count (int): Number of upcoming work anniversaries
            - anniversaries (list): List of employees with upcoming work anniversaries
            - total_event_count (int): Total number of upcoming events
    Raises:
        HTTPException: 
            - 400: If company_id is invalid or if any other error occurs during execution
            - 401: If user is not authorized (not an admin or doesn't belong to the company)
    Each birthday and anniversary entry in the returned lists contains:
        - _id (str): Employee ID
        - first_name (str): Employee's first name
        - last_name (str): Employee's last name
        - date_of_birth/employment_date (str): Original date in ISO format
        - this_year_birthday/this_year_anniversary (str): This year's date in ISO format
    """

    user, user_type = user_and_type
    
    if user_type != "admin":
        raise get_user_exception()
    
    company_id = user["company_id"] 

    try:
        data = {
            "birthday_count": 0,
            "birthdays": [],
            "anniversary_count": 0,
            "anniversaries": [],
            "total_event_count": 0
        }

        # Validate and sanitize company_id
        if not company_id.isalnum():
            raise HTTPException(status_code=400, detail="Invalid company ID")

        company = await companies_collection.find_one({"registration_number": company_id})
        if not company:
            return data
            
        if str(company.get("registration_number")) != str(user["company_id"]):
            raise get_user_exception()

        today = datetime.now(UTC)
        thirty_days = today + timedelta(days=30)

        try:
            # Get upcoming birthdays
            birthday_pipeline = [
                {
                    "$match": {
                        "company_id": company_id,
                        "employment_status": "active"
                    }
                },
                {
                    "$project": {
                        "first_name": 1,
                        "last_name": 1,
                        "date_of_birth": 1,
                        "this_year_birthday": {
                            "$dateFromParts": {
                                "year": {"$year": today},
                                "month": {"$month": "$date_of_birth"},
                                "day": {"$dayOfMonth": "$date_of_birth"}
                            }
                        }
                    }
                },
                {
                    "$match": {
                        "this_year_birthday": {
                            "$gte": today,
                            "$lte": thirty_days
                        }
                    }
                },
                {
                    "$sort": {"this_year_birthday": 1}
                }
            ]
            birthdays = await employees_collection.aggregate(birthday_pipeline).to_list(None)
        except Exception:
            birthdays = []

        try:
            # Get upcoming work anniversaries
            anniversary_pipeline = [
                {
                    "$match": {
                        "company_id": company_id,
                        "employment_status": "active"
                    }
                },
                {
                    "$project": {
                        "first_name": 1,
                        "last_name": 1,
                        "employment_date": 1,
                        "this_year_anniversary": {
                            "$dateFromParts": {
                                "year": {"$year": today},
                                "month": {"$month": "$employment_date"},
                                "day": {"$dayOfMonth": "$employment_date"}
                            }
                        }
                    }
                },
                {
                    "$match": {
                        "this_year_anniversary": {
                            "$gte": today,
                            "$lte": thirty_days
                        }
                    }
                },
                {
                    "$sort": {"this_year_anniversary": 1}
                }
            ]
            anniversaries = await employees_collection.aggregate(anniversary_pipeline).to_list(None)
        except Exception:
            anniversaries = []

        # Convert ObjectId and datetime fields to string
        for birthday in birthdays:
            if "_id" in birthday:
                birthday["_id"] = str(birthday["_id"])
            if "date_of_birth" in birthday:
                birthday["date_of_birth"] = birthday["date_of_birth"].isoformat()
            if "this_year_birthday" in birthday:
                birthday["this_year_birthday"] = birthday["this_year_birthday"].isoformat()

        for anniversary in anniversaries:
            if "_id" in anniversary:
                anniversary["_id"] = str(anniversary["_id"])
            if "employment_date" in anniversary:
                anniversary["employment_date"] = anniversary["employment_date"].isoformat()
            if "this_year_anniversary" in anniversary:
                anniversary["this_year_anniversary"] = anniversary["this_year_anniversary"].isoformat()

        data.update({
            "birthday_count": len(birthdays),
            "birthdays": birthdays,
            "anniversary_count": len(anniversaries),
            "anniversaries": anniversaries,
            "total_event_count": len(birthdays) + len(anniversaries)
        })

        return data

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"an error occurred - {e}")