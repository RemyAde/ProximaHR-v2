from datetime import datetime
from bson import ObjectId
from typing import List
from pymongo.collection import Collection


def calculate_ideal_monthly_hours(working_hours: float, week_days: int, month_days: int, leave_days: List[datetime]) -> float:
    """Calculate ideal working hours for the month, excluding leave days."""
    weeks_in_month = month_days / 7
    total_work_days = weeks_in_month * week_days
    leave_days_in_month = len([day for day in leave_days if day.month == datetime.now().month])
    effective_work_days = total_work_days - leave_days_in_month
    return effective_work_days * working_hours


def calculate_attendance_status(hours_worked: float, working_hours: float, is_leave_day: bool) -> str:
    """Determine attendance status based on hours worked or leave."""
    if is_leave_day:
        return "on leave"
    if hours_worked >= 0.9 * working_hours:
        return "present"
    elif hours_worked >= 0.4 * working_hours:
        return "undertime"
    else:
        return "absent"
    

def calculate_monthly_attendance_percentage(actual_hours: float, ideal_hours: float) -> float:
    """Calculate monthly attendance percentage."""
    return (actual_hours / ideal_hours) * 100 if ideal_hours > 0 else 0


def calculate_overtime_hours(hours_worked: float, working_hours: float) -> float:
    """Calculate overtime hours for a day."""
    return max(0, hours_worked - working_hours)


async def log_timer(employee_id: str, action: str, employees_collection: Collection, timestamp: datetime):
    """Start, stop, or pause/resume the timer."""
    employee = await employees_collection.find_one({"employee_id": ObjectId(employee_id)})
    if not employee:
        raise ValueError("Employee not found")
    
    # Timer actions
    if action == "start":
        await employees_collection.update_one(
            {"employee_id": employee["_id"]},
            {"$set": {"timer.start_time": timestamp, "timer.end_time": None, "timer.paused_time": []}}
        )
    elif action == "pause":
        await employees_collection.update_one(
            {"employee_id": employee["_id"]},
            {"$push": {"timer.paused_time": timestamp}}
        )
    elif action == "stop":
       await  employees_collection.update_one(
            {"employee_id": employee["_id"]},
            {"$set": {"timer.end_time": timestamp}}
        )