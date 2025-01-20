from datetime import datetime, timedelta


def calculate_attendance_status(hours_worked: float, working_hours: float, is_leave_day: bool) -> str:
    if is_leave_day:
        return "on_leave"
    if hours_worked >= 0.9 * working_hours:
        return "present"
    elif hours_worked >= 0.4 * working_hours:
        return "undertime"
    else:
        return "absent"


async def get_ideal_monthly_hours(weekly_workdays: int, working_hours: int, month: int, year: int) -> float:
    """Calculate ideal working hours for the month."""
    total_days = (datetime(year, month % 12 + 1, 1) - timedelta(days=1)).day
    weekdays = sum(1 for day in range(1, total_days + 1)
                   if datetime(year, month, day).weekday() < weekly_workdays)
    return weekdays * working_hours