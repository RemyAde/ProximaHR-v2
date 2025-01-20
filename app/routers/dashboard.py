from datetime import datetime, timedelta
from pytz import UTC
from fastapi import APIRouter, HTTPException, Depends, status
from app.utils.report_analytics_utils import calculate_attendance_trend
from db import companies_collection, employees_collection, departments_collection, leaves_collection, timer_logs_collection
from app.utils.app_utils import get_current_user
from exceptions import get_user_exception, get_unknown_entity_exception
from app.utils.dashboard_utils import get_upcoming_events_for_the_month

router = APIRouter()


@router.get("/company-overview")
async def get_company_info(company_id, user_and_type: tuple = Depends(get_current_user)):
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
    
    try:
        data = {}
        company = await companies_collection.find_one({"registration_number": company_id})
        if not company:
            raise get_unknown_entity_exception()
        
        if str(company.get("registration_number")) != str(user["company_id"]):
            raise get_user_exception()
       
        staff_size = company.get("staff_size")

        department_count = await departments_collection.count_documents({"company_id": company_id})

        pending_leave_count = await leaves_collection.count_documents({"company_id": company_id, "status": "pending"})

        attendance_percentage = await calculate_attendance_trend(user["company_id"], employees_collection, timer_logs_collection)
        
        data.update({
            "total_employees": staff_size,
            "department_count": department_count,
            "pending_leave_count": pending_leave_count,
            "attendance_percentage": attendance_percentage
        })

        return data

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"an error occured - {e}")
    

@router.get("/department-overview")
async def department_overview(company_id: str, user_and_type: tuple = Depends(get_current_user)):
    """
    Retrieves department overview data for a specific company.
    This asynchronous function provides various metrics related to company departments,
    including department count, attendance rates, leave statistics, and average working hours.\n
    Args:
        company_id (str): The registration number of the company to get overview for.
        user_and_type (tuple): A tuple containing user information and type, obtained from dependency injection.
                              Expected format: (user_dict, user_type_str).\n
    Returns:
        dict: A dictionary containing the following metrics:
            - department_count (int): Total number of departments in the company
            - attendance_rate (float): Current month's attendance rate
            - approved_leave_count (int): Total count of approved leaves
            - active_leave_count (int): Count of currently active approved leaves
            - average_hours_worked (float): Average working hours for the current month\n
    Raises:
        HTTPException: If user is not admin, company not found, or other processing errors occur
        UserException: If user is not authorized to access company data
        UnknownEntityException: If the specified company does not exist\n
    Requires:
        - Admin level access
        - User must belong to the specified company
    """

    user, user_type = user_and_type

    if user_type != "admin":
        raise get_user_exception()
    
    try:
        data = {}
        company = await companies_collection.find_one({"registration_number": company_id})
        if not company:
            raise get_unknown_entity_exception()
        
        if str(company.get("registration_number")) != str(user["company_id"]):
            raise get_user_exception()
        
        department_count = await departments_collection.count_documents({"company_id": company_id})
        approved_leave_count = await leaves_collection.count_documents({"company_id": company_id, "status": "approved"})

        s = [{"$match": {"company_id": company_id, "status": "approved"}}, 
            {"$match": {"end_date": {"$gte": datetime.now(UTC)}}}, 
            {"$count": "count"}]
        active_leave = await leaves_collection.aggregate(s).to_list(1)
        active_leave = active_leave[0]["count"] if active_leave else 0

        attendance_rate = await calculate_attendance_trend(user["company_id"], employees_collection, timer_logs_collection)

        # Calculate average working hours for current month
        current_month = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        next_month = (current_month.replace(day=28) + timedelta(days=4)).replace(day=1)

        average_hours_pipeline = [
            {"$match": {
                "company_id": company_id,
                "date": {"$gte": current_month, "$lt": next_month}
            }},
            {"$group": {
                "_id": None,
                "average_hours": {"$avg": "$total_hours"}
            }}
        ]

        average_hours_result = await timer_logs_collection.aggregate(average_hours_pipeline).to_list(1)
        average_hours = round(average_hours_result[0]["average_hours"], 2) if average_hours_result else 0

        data.update({
            "department_count": department_count,
            "attendance_rate": attendance_rate["current_month_attendance_rate"],
            "approved_leave_count": approved_leave_count,
            "active_leave_count": active_leave,
            "average_hours_worked": average_hours
        })

        return data
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"an error occured - {e}")

    
@router.get("/leave-overview")
async def leave_overview(company_id: str, user_and_type: tuple = Depends(get_current_user)):
    """
    Retrieve leave statistics overview for a specific company.
    This async function provides three key metrics for leave management:
    - Number of pending leave requests
    - Number of approved leaves for the current month
    - Overall leave approval rate (percentage)\n
    Args:
        company_id (str): The registration number of the company
        user_and_type (tuple): Tuple containing user info and type, obtained via dependency injection.
                              First element is user dict, second is user type string.\n
    Returns:
        dict: A dictionary containing:
            - pending_leaves (int): Count of pending leave requests
            - monthly_approved_leaves (int): Count of approved leaves for current month
            - leave_approval_rate (float): Percentage of total leaves that were approved\n
    Raises:
        HTTPException: If database operation fails or if invalid request
        UserException: If user is not admin or doesn't belong to the specified company\n
    Required Permissions:
        - User must be an admin
        - User must belong to the specified company
    """

    user, user_type = user_and_type
    if user_type != "admin":
        raise get_user_exception()
    try:
        company = await companies_collection.find_one({"registration_number": company_id})
        if not company or str(company.get("registration_number")) != str(user["company_id"]):
            raise get_user_exception()
        pending_count = await leaves_collection.count_documents({
            "company_id": company_id,
            "status": "pending"
        })
        current_month = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        next_month = (current_month.replace(day=28) + timedelta(days=4)).replace(day=1)
        monthly_approved = await leaves_collection.count_documents({
            "company_id": company_id,
            "status": "approved",
            "start_date": {"$gte": current_month, "$lt": next_month}
        })
        total_leaves = await leaves_collection.count_documents({"company_id": company_id})
        total_approved = await leaves_collection.count_documents({
            "company_id": company_id,
            "status": "approved"
        })
        approval_rate = (total_approved / total_leaves * 100) if total_leaves > 0 else 0
        return {
            "pending_leaves": pending_count,
            "monthly_approved_leaves": monthly_approved,
            "leave_approval_rate": round(approval_rate, 2)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"an error occurred - {e}")
    

@router.get("/payroll-overview")
async def payroll_overview(company_id: str, user_and_type: tuple = Depends(get_current_user)):
    """
    Retrieves payroll overview data for a specific company.
    This async function calculates and returns key payroll metrics including total cost,
    payment status, and next payroll date for a given company. Only accessible by admin users.\n
    Args:
        company_id (str): The registration number of the company
        user_and_type (tuple): A tuple containing user info and type, obtained from get_current_user dependency\n
    Returns:
        dict: A dictionary containing:
            - total_payroll_cost (float): Total cost of all employee compensations rounded to 2 decimals
            - paid_percentage (float): Percentage of employees who have been paid rounded to 2 decimals
            - paid_employees (int): Number of employees with "paid" payment status
            - next_payroll_date (date): Date of the next payroll cycle\n
    Raises:
        HTTPException: If user authentication fails or if there's an error processing the request
        UserException: If user is not an admin or doesn't belong to the specified company\n
    Notes:
        Total payroll cost includes base salary and all allowances (overtime, housing, 
        transport, medical, and company match contributions)
    """

    user, user_type = user_and_type
    if user_type != "admin":
        raise get_user_exception()
    
    try:
        company = await companies_collection.find_one({"registration_number": company_id})
        if not company or str(company.get("registration_number")) != str(user["company_id"]):
            raise get_user_exception()

        pipeline = [
            {"$match": {"company_id": company_id}},
            {"$group": {
                "_id": None,
                "total_cost": {
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
                },
                "total_employees": {"$sum": 1},
                "paid_employees": {
                    "$sum": {"$cond": [{"$eq": ["$payment_status", "paid"]}, 1, 0]}
                }
            }}
        ]

        result = await employees_collection.aggregate(pipeline).to_list(1)
        payroll_data = result[0] if result else {"total_cost": 0, "total_employees": 0, "paid_employees": 0}

        paid_percentage = (payroll_data["paid_employees"] / payroll_data["total_employees"] * 100) if payroll_data["total_employees"] > 0 else 0

        today = datetime.now(UTC)
        last_day_current = (today.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        next_payroll = last_day_current if today.date() < last_day_current.date() else (last_day_current + timedelta(days=32)).replace(day=1) - timedelta(days=1)

        return {
            "total_payroll_cost": round(payroll_data["total_cost"], 2),
            "paid_percentage": round(paid_percentage, 2),
            "paid_employees": payroll_data["paid_employees"],
            "next_payroll_date": next_payroll.date()
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"an error occurred - {e}")


@router.get("/events")
async def get_events(company_id:str, user_and_type: tuple = Depends(get_current_user)):
    """
    Retrieves upcoming birthdays and anniversaries for a company.
    This asynchronous function fetches and compiles birthday and anniversary events for employees
    in a specified company. It performs authorization checks to ensure only admin users
    can access their own company's data.\n
    Args:
        company_id (str): The registration number of the company
        user_and_type (tuple): A tuple containing user information and user type, obtained from get_current_user\n
    Returns:
        dict: A dictionary containing:
            - birthday_count (int): Number of upcoming birthdays
            - birthdays (list): List of upcoming birthday events
            - anniversary_count (int): Number of upcoming anniversaries
            - anniversaries (list): List of upcoming anniversary events
            - total_event_count (int): Total number of upcoming events\n
    Raises:
        HTTPException: When company is not found or user is not authorized
    """

    data = {}

    company = await companies_collection.find_one({"registration_number": company_id})
    if not company:
        raise get_unknown_entity_exception()
    
    user, user_type = user_and_type
    if user_type != "admin":
        raise get_user_exception()
    
    if str(company.get("registration_number")) != str(user.get("company_id")):
        raise get_user_exception()
    
    upcoming_birthdays = await get_upcoming_events_for_the_month(event_collection=employees_collection, company_id=company_id, date_field="date_of_birth", event_type="birthday")
    birthday_count = len(upcoming_birthdays)

    data.update(
        {"birthday_count": birthday_count, "birthdays": upcoming_birthdays}
    )

    upcoming_anniversaries = await get_upcoming_events_for_the_month(event_collection=employees_collection, company_id=company_id, date_field="employment_date", event_type="anniversary")
    anniversary_count = len(upcoming_anniversaries)

    total_event_count = birthday_count + anniversary_count

    data.update(
        {"anniversary_count": anniversary_count,
         "anniversaries": upcoming_anniversaries,
         "total_event_count": total_event_count}
    )
    
    return data