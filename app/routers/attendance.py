from datetime import datetime, timedelta
from typing import Dict, List
from bson import ObjectId
from pytz import UTC
from fastapi import APIRouter, Depends, HTTPException, Query
from db import employees_collection, timer_logs_collection, leaves_collection
from models.attendance import TimerLog
from utils.attendance_utils import (calculate_attendance_status, get_ideal_monthly_hours, 
                                    get_attendance_summary_for_employee, calculate_attendance_totals,
                                    get_employee_monthly_report)
from utils.app_utils import get_current_user

router = APIRouter()

@router.post("/employee/timer/start")
async def start_timer(user_and_type: tuple = Depends(get_current_user)):
    """
    Starts a timer log for an employee's attendance.
    This function creates a new timer log entry in the database with the current timestamp
    for a specific employee within their company.
    Args:
        user_and_type (tuple): A tuple containing user information and user type, obtained from get_current_user dependency.
                              user: Dictionary containing 'company_id' and 'employee_id'
                              user_type: The type/role of the user
    Returns:
        dict: A dictionary with a success message if timer starts successfully
            Example: {"message": "Timer started successfully"}
    Raises:
        HTTPException: If there's an error during the timer creation process
            - status_code: 400
            - detail: Error message with the specific exception details
    """
    user, user_type = user_and_type
    if user_type != "employee":
        raise HTTPException(status_code=403, detail="Only employees can start timers")

    try:
        now = datetime.now(UTC)
        timer_log = TimerLog(company_id=user.get("company_id"), employee_id=user.get("employee_id"), start_time=now, date=now)
        await timer_logs_collection.insert_one(timer_log.model_dump())
        return {"message": "Timer started successfully"}
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"An exception occured - {e}")


@router.post("/employee/timer/pause")
async def pause_timer(user_and_type: tuple = Depends(get_current_user)):
    """
    Pauses an active timer for the current user.
    This function adds a new pause interval to the user's active timer log. It finds the active timer
    by looking for a timer log with no end_time and adds a new pause interval with the current time
    as the start time.
    Args:
        user_and_type (tuple): A tuple containing the user object and user type, obtained from get_current_user dependency.
                              The user object must contain 'company_id' and 'employee_id'.
    Returns:
        dict: A dictionary containing a success message if the timer was successfully paused.
              Example: {"message": "Timer paused"}
    Raises:
        HTTPException: 
            - 404 if no active timer is found
            - 400 if any other error occurs during the operation
    Dependencies:
        - get_current_user
        - timer_logs_collection (MongoDB collection)
    """
    user, user_type = user_and_type
    if user_type != "employee":
        raise HTTPException(status_code=403, detail="Only employees can pause timers")

    try:
        now = datetime.now(UTC)
        timer_log = await timer_logs_collection.find_one({"company_id":user.get("company_id"), "employee_id": user.get("employee_id"), "end_time": None})
        if not timer_log:
            raise HTTPException(status_code=404, detail="Active timer not found")

        paused_intervals = timer_log.get("paused_intervals", [])
        paused_intervals.append({"start": now})
        await timer_logs_collection.update_one({"_id": timer_log["_id"]}, {"$set": {"paused_intervals": paused_intervals}})
        return {"message": "Timer paused"}
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"An exception occured - {e}")


@router.post("/employee/timer/resume")
async def resume_timer(user_and_type: tuple = Depends(get_current_user)):
    """
    Resume a previously paused timer for a user.
    This function finds the most recent timer log for the user that is currently paused
    and adds an end timestamp to the latest pause interval, effectively resuming the timer.
    Args:
        user_and_type (tuple): A tuple containing the user object and user type,
                              obtained from the get_current_user dependency.
    Returns:
        dict: A dictionary containing a success message
            Example: {"message": "Timer resumed"}
    Raises:
        HTTPException: 
            - 404 if no paused timer is found
            - 400 if the timer is not currently paused
            - 400 if any other error occurs during execution
    Dependencies:
        - get_current_user
        - timer_logs_collection (MongoDB collection)
    """

    user, user_type = user_and_type
    if user_type != "employee":
        raise HTTPException(status_code=403, detail="Only employees can resume timers")

    try:
        now = datetime.now(UTC)
        timer_log = await timer_logs_collection.find_one({"company_id":user.get("company_id"), "employee_id": user.get("employee_id"), "end_time": None})
        if not timer_log or not timer_log.get("paused_intervals"):
            raise HTTPException(status_code=404, detail="Paused timer not found")

        paused_intervals = timer_log["paused_intervals"]
        if "end" in paused_intervals[-1]:
            raise HTTPException(status_code=400, detail="Timer is not paused")

        paused_intervals[-1]["end"] = now
        await timer_logs_collection.update_one({"_id": timer_log["_id"]}, {"$set": {"paused_intervals": paused_intervals}})
        
        return {"message": "Timer resumed"}
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"An exception occurd - {e}")


@router.post("/employee/timer/stop")
async def stop_timer(user_and_type: tuple = Depends(get_current_user)):
    """
    Stops an active timer for the current user and calculates total worked hours.
    This function finds the active timer for the user, calculates the total hours worked
    (excluding any paused intervals), and updates the timer log with the end time and 
    total hours worked.
    Args:
        user_and_type (tuple): A tuple containing user information and user type, obtained from get_current_user dependency.
            The user dict contains 'company_id' and 'employee_id'.
    Returns:
        dict: A dictionary containing:
            - message (str): Confirmation message "Timer stopped"
            - total_hours (float): Total hours worked, excluding paused intervals
    Raises:
        HTTPException: 
            - 404 if no active timer is found
            - 400 if any other error occurs during execution
    Notes:
        - All datetime calculations are performed in UTC
        - Handles both timezone-aware and naive datetime objects by assuming UTC for naive ones
        - Takes into account paused intervals when calculating total hours worked
    """

    user, user_type = user_and_type
    if user_type != "employee":
        raise HTTPException(status_code=403, detail="Only employees can stop timers")

    try:
        now = datetime.now(UTC)  # Offset-aware datetime
        timer_log = await timer_logs_collection.find_one({"company_id":user.get("company_id"), "employee_id": user.get("employee_id"), "end_time": None})
        if not timer_log:
            raise HTTPException(status_code=404, detail="Active timer not found")

        # Convert `start_time` from the database to a timezone-aware datetime
        start_time = timer_log["start_time"]
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=UTC)  # Assume UTC if tzinfo is missing

        # Calculate total hours worked, excluding paused intervals
        total_hours = (now - start_time).total_seconds() / 3600
        for interval in timer_log.get("paused_intervals", []):
            if "end" in interval:
                pause_start = interval["start"]
                pause_end = interval["end"]
                # Ensure paused intervals are timezone-aware
                if pause_start.tzinfo is None:
                    pause_start = pause_start.replace(tzinfo=UTC)
                if pause_end.tzinfo is None:
                    pause_end = pause_end.replace(tzinfo=UTC)
                total_hours -= (pause_end - pause_start).total_seconds() / 3600

        # Update the timer log with total hours
        await timer_logs_collection.update_one(
            {"_id": timer_log["_id"]},
            {"$set": {"end_time": now, "total_hours": total_hours}}
        )
        return {"message": "Timer stopped", "total_hours": total_hours}
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"An exception occured - {e}")


@router.get("/employee/daily-attendance")
async def calculate_daily_attendance(
    is_leave_day: bool = Query(False, description="True/Fale or 1/0 for employee on leave or not"),
    user_and_type: tuple = Depends(get_current_user)
    ):
    """
    Returns the just concluded attendance timer value.\n 
    Hit this endpoint when attendance timer has been stopped.
    """
    user, user_type = user_and_type
    if user_type != "employee":
        raise HTTPException(status_code=403, detail="Only employees can access this endpoint")
    
    try:
        today = datetime.now(UTC).date()
        today_start = datetime(today.year, today.month, today.day)  # Start of the day
        today_end = datetime(today.year, today.month, today.day, 23, 59, 59)  # End of the day

        timer_logs = await timer_logs_collection.find({
            "company_id": user.get("company_id"),
            "employee_id": user.get("employee_id"),
            "date": {"$gte": today_start, "$lte": today_end}
            }).to_list(length=None)
        
        
        # timer_logs = await timer_logs_collection.find({"company_id":user.get("company_id"), "employee_id": user.get("employee_id"), "date": today}).to_list(length=None)
        total_hours_worked = sum(log.get("total_hours", 0) for log in timer_logs)

        employee = await employees_collection.find_one({"_id": ObjectId(user.get("_id"))})
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found")

        working_hours = employee.get("working_hours", 0)
        overtime_hours = max(0, total_hours_worked - working_hours)
        attendance_status = calculate_attendance_status(total_hours_worked, working_hours, is_leave_day)

        await employees_collection.update_one(
            {"employee_id": employee["employee_id"]},
            {"$push": {"attendance": {
                "date": today_start,
                "hours_worked": total_hours_worked,
                "overtime_hours": overtime_hours,
                "attendance_status": attendance_status
            }},
            "$inc": {"monthly_overtime_hours": overtime_hours, "monthly_working_hours": total_hours_worked}}
        )

        return {"attendance_status": attendance_status, "hours_worked": total_hours_worked}
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"An exception occured - {e}")

    
@router.get("/employee/attendance-summary")
async def get_attendance_summary(user_and_type: tuple = Depends(get_current_user)):
    """
    This function fetches and analyzes attendance data for the employee within the current month,
    including approved leaves, work hours, and various attendance statuses. It also returns the
    attendance percentage for the month and the total overtime hours.
    
    Returns:
        dict: A dictionary containing:
            - totals (dict): Summary counts including:
                - leave_days (int): Total number of approved leave days
                - absences (int): Total number of absences
                - undertimes (int): Total number of undertime days
                - presents (int): Total number of present days
            - attendance_percentage (float): The percentage of ideal hours met for the month
            - total_overtime_hours (float): Aggregate overtime hours for the month
    Raises:
        HTTPException: 
            - 400 if employee is not found in the company
    Notes:
        - An employee is considered:
            - Present: if worked >= 90% of required hours
            - Undertime: if worked between 40% and 90% of required hours
            - Absent: if worked < 40% of required hours
    """
    user, user_type = user_and_type
    if user_type != "employee":
        raise HTTPException(status_code=403, detail="Only employees can access this endpoint")

    employee = await employees_collection.find_one({
        "_id": ObjectId(user.get("_id")),
        "company_id": user.get("company_id")
    })
    if not employee:
        raise HTTPException(status_code=400, detail="Employee record not found")
    
    today = datetime.now(UTC)
    start_date = datetime(today.year, today.month, 1, tzinfo=UTC)
    end_date = today

    # Fetch approved leaves for the employee
    leaves = await leaves_collection.find({
        "company_id": employee["company_id"], 
        "employee_id": employee.get("employee_id"),
        "status": "approved",
        "start_date": {"$lte": end_date},
        "end_date": {"$gte": start_date}
    }).to_list(length=None)

    leave_dates = set()
    for leave in leaves:
        leave_start = leave["start_date"].date()
        leave_end = leave["end_date"].date()
        for i in range((leave_end - leave_start).days + 1):
            leave_dates.add(leave_start + timedelta(days=i))

    # Fetch attendance logs for the month
    attendance_logs = await timer_logs_collection.find({
        "company_id": employee["company_id"],
        "employee_id": employee.get("employee_id"),
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

        if is_leave_day:
            attendance_status = "on_leave"
            total_leave_days += 1
            hours_worked = 0
            overtime_flag = 0
            undertime_flag = 0
            absent = 0
        else:
            log = logs_by_date.get(current_day)
            if log:
                start_time = log.get("start_time")
                end_time = log.get("end_time")
                if start_time and end_time:
                    hours_worked = (end_time - start_time).total_seconds() / 3600
                else:
                    hours_worked = 0

                if hours_worked > working_hours:
                    overtime_flag = 1
                else:
                    overtime_flag = 0

                undertime_flag = 1 if working_hours > hours_worked >= 0.4 * working_hours else 0
                absent = 1 if hours_worked < 0.4 * working_hours else 0

                if hours_worked >= 0.9 * working_hours:
                    attendance_status = "present"
                    total_presents += 1
                elif undertime_flag:
                    attendance_status = "undertime"
                    total_undertimes += 1
                elif absent:
                    attendance_status = "absent"
                    total_absences += 1
                else:
                    attendance_status = "absent"
                    total_absences += 1
            else:
                hours_worked = 0
                overtime_flag = 0
                undertime_flag = 0
                absent = 1
                attendance_status = "absent"
                total_absences += 1

        summary.append({
            "date": current_day,
            "attendance_status": attendance_status,
            "hours_worked": round(hours_worked, 2),
            "overtime": overtime_flag,
            "undertime": undertime_flag,
            "absent": absent
        })

        current_date += timedelta(days=1)

    # Calculate total actual hours and total overtime hours for the month
    total_actual_hours = sum(record["hours_worked"] for record in summary)
    total_overtime_hours = sum(max(0, record["hours_worked"] - working_hours) for record in summary)

    # Calculate ideal hours using weekly_workdays and working_hours from employee record
    weekly_workdays = int(employee.get("weekly_workdays", 5))
    ideal_hours = await get_ideal_monthly_hours(
        weekly_workdays=weekly_workdays, 
        working_hours=int(working_hours), 
        month=today.month, 
        year=today.year
    )
    
    attendance_percentage = (total_actual_hours / ideal_hours) * 100 if ideal_hours > 0 else 0

    # Return detailed attendance and summary counts along with the attendance percentage and total overtime hours
    return {
        # "attendance_summary": summary,
        "totals": {
            "leave_days": total_leave_days,
            "absences": total_absences,
            "undertimes": total_undertimes,
            "presents": total_presents,
            "total_overtime_hours": round(total_overtime_hours, 2)
        },
        "attendance_percentage": round(attendance_percentage, 2),
    }


@router.get("/employee/attendance-tracking", response_model=List[Dict])
async def get_attendance_and_tracking_details(
    year: int = Query(..., description="Year for the attendance report"),
    month: int = Query(..., description="Month for the attendance report"),
    user_and_type: tuple = Depends(get_current_user)
):
    """
    Endpoint to return daily attendance summary for the current employee.
    """
    user, user_type = user_and_type
    if user_type != "employee":
        raise HTTPException(status_code=403, detail="Only employees can access this endpoint")
    
    employee = await employees_collection.find_one({"_id": ObjectId(user.get("_id"))})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    summary = await get_attendance_summary_for_employee(employee, month, year)
    return summary


@router.get("/employee/attendance-totals", response_model=Dict)
async def attendance_totals(
    year: int = Query(..., description="Year for the attendance report"),
    month: int = Query(..., description="Month for the attendance report"),
    user_and_type: tuple = Depends(get_current_user)
):
    """
    Endpoint to return aggregated attendance totals for the current employee.
    Totals include total present days, absent days, overtime hours, and undertime hours.
    """
    user, user_type = user_and_type
    if user_type != "employee":
        raise HTTPException(status_code=403, detail="Only employees can access this endpoint")
    
    employee = await employees_collection.find_one({"_id": ObjectId(user.get("_id"))})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    totals = await calculate_attendance_totals(employee, month, year)
    return totals


@router.get("/employee/monthly-stats", response_model=Dict)
async def employee_monthly_stats(
    month: int = Query(..., description="Month for the report"),
    year: int = Query(..., description="Year for the report"),
    user_and_type: tuple = Depends(get_current_user)
):
    """
    Returns the current employee's monthly report including:
      - Attendance percentage for the month,
      - Annual leave balance,
      - Net pay,
      - Total overtime hours for the month.
    """
    user, user_type = user_and_type
    if user_type != "employee":
        raise HTTPException(status_code=403, detail="Only employees can access this endpoint")
    
    employee = await employees_collection.find_one({"_id": ObjectId(user.get("_id")), "company_id": user.get("company_id")})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    report = await get_employee_monthly_report(employee, month, year)
    return report