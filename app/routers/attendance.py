from datetime import datetime, timedelta
from typing import Dict, List
from bson import ObjectId
from pytz import UTC
from fastapi import APIRouter, Depends, HTTPException, Query
from db import employees_collection, timer_logs_collection
from models.attendance import TimerLog
from attendance_utils import (calculate_attendance_status, get_ideal_monthly_hours)
from utils import get_current_user

router = APIRouter()

@router.post("/employee/timer/start")
async def start_timer(user_and_type: tuple = Depends(get_current_user)):
    user, user_type = user_and_type

    try:
        now = datetime.now(UTC)
        timer_log = TimerLog(company_id=user.get("company_id"), employee_id=user.get("employee_id"), start_time=now, date=now)
        await timer_logs_collection.insert_one(timer_log.model_dump())
        return {"message": "Timer started successfully"}
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"An exception occured - {e}")


@router.post("/employee/timer/pause")
async def pause_timer(user_and_type: tuple = Depends(get_current_user)):
    user, user_type = user_and_type

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
    user, user_type = user_and_type

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
    user, user_type = user_and_type

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
            {"employee_id": employee["_id"]},
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


@router.get("/employee/monthly-attendance")
async def calculate_monthly_attendance(month: int, year: int, user_and_type: tuple = Depends(get_current_user)):
    user, user_type = user_and_type

    try:
        employee = await employees_collection.find_one({"_id": ObjectId(user.get("_id"))})
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found")

        weekly_workdays = employee.get("weekly_workdays", 0)
        working_hours = employee.get("working_hours", 0)
        ideal_hours = await get_ideal_monthly_hours(weekly_workdays=int(weekly_workdays), working_hours=int(working_hours), month=month, year=year)
        actual_hours = employee.get("monthly_working_hours", 0)
        attendance_percentage = (actual_hours / ideal_hours) * 100

        return {
            "employee_id": str(user.get("_id")),
            "month": month,
            "year": year,
            "attendance_percentage": attendance_percentage,
            "ideal_hours": ideal_hours,
            "actual_hours": actual_hours
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"An exception occured - {e}")


# @router.get("/employee/weekly-attendance")
# async def get_weekly_attendance(
#     year: int = Query(..., description="Year for the attendance report"),
#     month: int = Query(..., description="Month for the attendance report"),
#     user_and_type: tuple = Depends(get_current_user)
# ) -> List[Dict]:
#     """
#     Generate weekly attendance report for an employee for a chosen month and year.
#     """
#     user, user_type = user_and_type
#     try:
#         # Verify employee existence
#         employee = await employees_collection.find_one({"_id": ObjectId(user.get("_id"))})
#         if not employee:
#             raise HTTPException(status_code=404, detail="Employee not found")

#         # Fetch working hours
#         working_hours = int(employee.get("working_hours"))
#         weekly_workdays = int(employee.get("weekly_workdays"))
#         workdays = list(range(weekly_workdays))

#         # Initialize start and end dates for the month
#         start_date = datetime(year, month, 1, tzinfo=UTC)
#         end_date = (start_date + timedelta(days=31)).replace(day=1) - timedelta(days=1)

#         today = datetime.now(UTC)
#         today_date = today.date()  # Convert to a date object

#         # Adjust end_date for the current month
#         if year == today_date.year and month == today_date.month:
#             end_date = today

#         # Fetch attendance logs for the month
#         timer_logs = await timer_logs_collection.find({
#             "company_id": user.get("company_id"),
#             "employee_id": user.get("employee_id"),
#             "date": {"$gte": start_date, "$lte": end_date}
#         }).to_list(length=None)

#         # Organize logs by date for quick lookup
#         logs_by_date = {log["date"].date(): log for log in timer_logs}

#         # Generate weekly attendance summary
#         attendance_summary = []
#         current_date = start_date
#         while current_date <= end_date:
#             log = logs_by_date.get(current_date.date())

#             # Calculate attendance details
#             start_time = log["start_time"] if log else None
#             end_time = log["end_time"] if log else None
#             hours_worked = log.get("total_hours", 0) if log else 0

#             # Debugging output
#             print(f"Date: {current_date.date()}, Hours Worked: {hours_worked}, Working Hours: {working_hours}")

#             # Determine overtime, undertime, and absence
#             overtime = 1 if hours_worked > working_hours else 0
#             undertime = 1 if hours_worked < working_hours and hours_worked >= 0.4 * working_hours else 0
#             absent = 1 if hours_worked < 0.4 * working_hours else 0

#             # Append the daily attendance record
#             attendance_summary.append({
#                 "date": current_date.date(),
#                 "start_time": start_time,
#                 "end_time": end_time,
#                 "hours_worked": round(hours_worked, 2),
#                 "overtime": overtime,
#                 "undertime": undertime,
#                 "absent": absent
#             })

#             current_date += timedelta(days=1)

#         return attendance_summary

#     except Exception as e:
#         raise HTTPException(status_code=400, detail=f"An exception occurred - {e}")


@router.get("/employee/weekly-attendance")
async def get_weekly_attendance(
    year: int = Query(..., description="Year for the attendance report"),
    month: int = Query(..., description="Month for the attendance report"),
    user_and_type: tuple = Depends(get_current_user)
) -> List[Dict]:
    """
    Generate weekly attendance report for an employee for a chosen month and year.
    """
    user, user_type = user_and_type
    try:
        # Verify employee existence
        employee = await employees_collection.find_one({"_id": ObjectId(user.get("_id"))})
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found")

        # Fetch working hours
        working_hours = employee.get("working_hours")

        # Initialize start and end dates for the month
        start_date = datetime(year, month, 1, tzinfo=UTC)
        end_date = (start_date + timedelta(days=31)).replace(day=1) - timedelta(days=1)

        today = datetime.now(UTC)
        today_date = today.date()  # Convert to a date object

        # Adjust end_date for the current month
        if year == today_date.year and month == today_date.month:
            end_date = today

        # Fetch attendance logs for the month
        timer_logs = await timer_logs_collection.find({
            "company_id": user.get("company_id"),
            "employee_id": user.get("employee_id"),
            "date": {"$gte": start_date, "$lte": end_date}
        }).to_list(length=None)

        # Organize logs by date for quick lookup
        logs_by_date = {log["date"].date(): log for log in timer_logs}

        # Generate weekly attendance summary
        attendance_summary = []
        current_date = start_date
        
        while current_date <= end_date:
            # Check if current date is a weekday (Monday to Friday)
            if current_date.weekday() < 5:  # 0-4 corresponds to Monday-Friday
                log = logs_by_date.get(current_date.date())

                # Calculate attendance details
                start_time = log["start_time"] if log else None
                end_time = log["end_time"] if log else None
                hours_worked = log.get("total_hours", 0) if log else 0

                # Determine overtime, undertime, and absence
                if working_hours == 0:
                    absent = 1 if hours_worked == 0 else 0
                    attendance_summary.append({
                        "date": current_date.date(),
                        "start_time": start_time,
                        "end_time": end_time,
                        "hours_worked": round(hours_worked, 2),
                        "overtime": 0,
                        "undertime": 0,
                        "absent": absent
                    })
                else:
                    overtime = 1 if hours_worked > working_hours else 0
                    undertime = 1 if hours_worked < working_hours and hours_worked >= 0.4 * working_hours else 0
                    absent = 1 if hours_worked < 0.4 * working_hours else 0

                    attendance_summary.append({
                        "date": current_date.date(),
                        "start_time": start_time,
                        "end_time": end_time,
                        "hours_worked": round(hours_worked, 2),
                        "overtime": overtime,
                        "undertime": undertime,
                        "absent": absent
                    })

            # Move to the next day
            current_date += timedelta(days=1)

        return attendance_summary

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"An exception occurred - {e}")