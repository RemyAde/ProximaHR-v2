from datetime import datetime, timedelta
from bson import ObjectId
from fastapi import APIRouter, HTTPException, Depends, Path
from pytz import UTC
from db import leaves_collection, timer_logs_collection, employees_collection
from utils.app_utils import get_current_user
from utils.report_analytics_utils import calculate_attendance_trend

router = APIRouter()


@router.get("/attendance")
async def get_monthly_attendance_record(
    employee_id :str = Path(..., description="Employee ID"),
    user_and_type: tuple = Depends(get_current_user)
):
    """Retrieves and generates a monthly attendance record for a specific employee.
    This function fetches and analyzes attendance data for an employee within the current month,
    including approved leaves, work hours, and various attendance statuses.
    Args:
        employee_id (str): The unique identifier for the employee.
        user_and_type (tuple): A tuple containing user information and user type,
            obtained from the get_current_user dependency.
    Returns:
        dict: A dictionary containing:
            - attendance_summary (list): Daily attendance records with the following fields:
                - date (date): The date of the record
                - attendance_status (str): One of 'present', 'absent', 'undertime', or 'on_leave'
                - hours_worked (float): Number of hours worked, rounded to 2 decimal places
                - overtime (int): 1 if overtime was worked, 0 otherwise
                - undertime (int): 1 if undertime was recorded, 0 otherwise
                - absent (int): 1 if marked as absent, 0 otherwise
            - totals (dict): Summary counts including:
                - leave_days (int): Total number of approved leave days
                - absences (int): Total number of absences
                - undertimes (int): Total number of undertime days
                - presents (int): Total number of present days
    Raises:
        HTTPException: 
            - 403 if user is not an admin
            - 400 if employee is not found in the company
    Notes:
        - An employee is considered:
            - Present: if worked >= 90% of required hours
            - Undertime: if worked between 40% and 90% of required hours
            - Absent: if worked < 40% of required hours
    """

    user, user_type = user_and_type
    if user_type != "admin":
        raise HTTPException(status_code=403, detail="You are not authorized to perform this action")
    
    employee = await employees_collection.find_one({
        "employee_id": employee_id,
        "company_id": user.get("company_id")
    })
    if not employee:
        raise HTTPException(
            status_code=400,
            detail="Employee is not a member of your company"
        )
    
    today = datetime.now(UTC)
    start_date = datetime(today.year, today.month, 1, tzinfo=UTC)
    end_date = today

    # Fetch approved leaves for the employee
    leaves = await leaves_collection.find({
        "company_id": employee["company_id"], 
        "employee_id": employee["employee_id"],
        "status": "approved",
        "start_date": {"$lte": end_date},
        "end_date": {"$gte": start_date}
    }).to_list(length=None)

    leave_dates = set()
    for leave in leaves:
        leave_start = leave["start_date"].date()
        leave_end = leave["end_date"].date()
        leave_dates.update((leave_start + timedelta(days=i)) for i in range((leave_end - leave_start).days + 1))

    # Fetch attendance logs for the month
    attendance_logs = await timer_logs_collection.find({
        "company_id": employee.get("company_id", ""),
        "employee_id": employee.get("employee_id", ""),
        "date": {"$gte": start_date, "$lte": end_date}
    }).to_list(length=None)

    logs_by_date = {log["date"].date(): log for log in attendance_logs}

    # Get working hours for the employee
    working_hours = employee.get("working_hours", 8)

    # Generate attendance records
    summary = []
    current_date = start_date
    total_leave_days = 0
    total_absences = 0
    total_undertimes = 0
    total_presents = 0

    while current_date <= end_date:
        current_day = current_date.date()
        is_leave_day = current_day in leave_dates

        # Determine attendance status
        if is_leave_day:
            attendance_status = "on_leave"
            total_leave_days += 1
            hours_worked = 0
            overtime = 0
            undertime = 0
            absent = 0
        else:
            log = logs_by_date.get(current_day)
            if log:
                start_time = log.get("start_time")
                end_time = log.get("end_time")
                hours_worked = (end_time - start_time).total_seconds() / 3600 if start_time and end_time else 0
                overtime = 1 if hours_worked > working_hours else 0
                undertime = 1 if working_hours > hours_worked >= 0.4 * working_hours else 0
                absent = 1 if hours_worked < 0.4 * working_hours else 0

                if hours_worked >= 0.9 * working_hours:
                    attendance_status = "present"
                    total_presents += 1
                elif undertime:
                    attendance_status = "undertime"
                    total_undertimes += 1
                elif absent:
                    attendance_status = "absent"
                    total_absences += 1
            else:
                # No log means absent
                hours_worked = 0
                overtime = 0
                undertime = 0
                absent = 1
                attendance_status = "absent"
                total_absences += 1

        # Add attendance record
        summary.append({
            "date": current_day,
            "attendance_status": attendance_status,
            "hours_worked": round(hours_worked, 2),
            "overtime": overtime,
            "undertime": undertime,
            "absent": absent,
        })

        current_date += timedelta(days=1)

    # Return detailed attendance and summary counts
    return {
        "attendance_summary": summary,
        "totals": {
            "leave_days": total_leave_days,
            "absences": total_absences,
            "undertimes": total_undertimes,
            "presents": total_presents,
        }
    }


@router.get("/metrics")
async def get_metrics(user_and_type: tuple = Depends(get_current_user)):
    """
    Retrieve attendance metrics for a company.
    This endpoint requires admin privileges and returns the current month's attendance rate
    for all employees in the company.
    Args:
        user_and_type (tuple): A tuple containing user information and user type, obtained from
            the dependency get_current_user.
    Returns:
        dict: A dictionary containing:
            - attendance_rate (float): The attendance rate for the current month
    Raises:
        HTTPException:
            - 403: If the user is not an admin
    """
    user, user_type = user_and_type

    if user_type != "admin":
        raise HTTPException(status_code=403, detail="You are not authorized to perform this action")
    
    company_id = user["company_id"]

    today = datetime.now(UTC)
    start_date = datetime(today.year, today.month, 1, tzinfo=UTC)
    end_date = today

    # Fetch
    attendance_rate = await calculate_attendance_trend(company_id=company_id, employees_collection=employees_collection, 
                                                       timer_logs_collection=timer_logs_collection)
    return  {"attendance_rate": attendance_rate["current_month_attendance_rate"]}