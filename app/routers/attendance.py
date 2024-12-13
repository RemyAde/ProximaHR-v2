from datetime import datetime, timedelta
from bson import ObjectId
from pytz import UTC
from fastapi import APIRouter, Depends, HTTPException, Query
from db import employees_collection
from attendance_utils import (calculate_attendance_status, calculate_ideal_monthly_hours, 
                              calculate_monthly_attendance_percentage, calculate_overtime_hours, log_timer)
from utils import get_current_user

router = APIRouter()

@router.get("/employee/attendance")
async def get_employee_attendance(date: datetime, current_user: tuple = Depends(get_current_user)):
    """Get daily attendance for an employee."""

    user, user_type = current_user

    employee = employees_collection.find_one({"employee_id": ObjectId(user.get("_id"))})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    attendance = next((a for a in employee.get("attendance", []) if a["date"] == date.date()), None)
    if not attendance:
        raise HTTPException(status_code=404, detail="Attendance record not found")
    
    return attendance


@router.post("/employee/timer")
async def manage_timer(current_user: tuple = Depends(get_current_user), action: str = Query(..., description="start, pause, stop")):
    """Start, pause, or stop a timer."""

    user, user_type = current_user

    now = datetime.now(UTC)
    try:
        await log_timer(str(user.get("_id")), action, employees_collection, now)
        return {"message": f"Timer {action}ed successfully"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    

@router.post("/employee/attendance/update")
async def update_attendance(current_user: tuple = Depends(get_current_user)):
    """Update attendance for the current day."""

    user, user_type = current_user

    now = datetime.now(UTC)
    today = now.date()
    employee = await employees_collection.find_one({"employee_id": ObjectId(user.get("_id"))})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Check if today is a leave day
    is_leave_day = today in [leave.date() for leave in employee.get("leaves", [])]

    if is_leave_day: # might have to turn this to a cron job later on as employees on leaves might not log into the system
        attendance_status = "on leave"
        await employees_collection.update_one(
            {"employee_id": employee["_id"]},
            {"$push": {"attendance": {
                "date": today,
                "hours_worked": 0.0,
                "overtime_hours": 0.0,
                "attendance_status": attendance_status
            }}}
        )
        return {"message": "Attendance updated: Employee is on leave"}

    # Proceed with regular attendance calculation
    timer = employee.get("timer")
    if not timer or not timer.get("start_time"):
        raise HTTPException(status_code=400, detail="No timer record found")

    hours_worked = (timer["end_time"] - timer["start_time"]).total_seconds() / 3600
    for pause_start, pause_end in zip(timer.get("paused_time", [])[::2], timer.get("paused_time", [])[1::2]):
        hours_worked -= (pause_end - pause_start).total_seconds() / 3600

    overtime_hours = calculate_overtime_hours(hours_worked, employee["working_hours"])
    attendance_status = calculate_attendance_status(hours_worked, employee["working_hours"], is_leave_day=False)

    await employees_collection.update_one(
        {"employee_id": employee["_id"]},
        {"$push": {"attendance": {
            "date": today,
            "hours_worked": hours_worked,
            "overtime_hours": overtime_hours,
            "attendance_status": attendance_status
        }},
         "$inc": {"monthly_overtime_hours": overtime_hours, "monthly_working_hours": hours_worked}}
    )
    return {"message": "Attendance updated successfully"}


@router.get("/employee/attendance-summary")
async def get_attendance_summary(current_user: tuple = Depends(get_current_user)):
    """Get monthly attendance summary."""

    user, user_type = current_user

    now = datetime.now(UTC)
    employee = await employees_collection.find_one({"employee_id": ObjectId(user.get("_id"))})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    month_days = (now.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    leave_days = employee.get("leaves", [])
    ideal_hours = calculate_ideal_monthly_hours(employee["working_hours"], employee["week_days"], month_days.days, leave_days)
    actual_hours = employee["monthly_working_hours"]
    attendance_percentage = calculate_monthly_attendance_percentage(actual_hours, ideal_hours)

    return {
        "monthly_working_hours": actual_hours,
        "ideal_monthly_hours": ideal_hours,
        "attendance_percentage": attendance_percentage,
        "leave_days": len(leave_days)
    }