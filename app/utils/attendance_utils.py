from calendar import monthrange
from datetime import datetime, timedelta
from pytz import UTC

from fastapi import HTTPException
from db import employees_collection, timer_logs_collection, leaves_collection


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


async def calculate_department_metrics(company_id: str, month: int, year: int):
    """Calculate attendance rate, total overtime hours, total undertime hours, total absences, and total hours logged for each department."""
    try:
        # Define the start and end of the month
        start_of_month = datetime(year, month, 1, tzinfo=UTC)
        end_of_month = datetime(year, month, monthrange(year, month)[1], tzinfo=UTC)

        # Fetch all employees for the company
        employees = await employees_collection.find({"company_id": company_id, "employment_status": "active"}).to_list(length=None)
        if not employees:
            raise ValueError("No employees found for the company.")

        # Fetch attendance logs for the month and company
        logs_query = {
            "company_id": company_id,
            "date": {"$gte": start_of_month, "$lte": end_of_month}
        }
        logs = await timer_logs_collection.find(logs_query).to_list(length=None)

        # Group logs by employee and date
        logs_by_date = {}
        for log in logs:
            logs_by_date.setdefault(log["employee_id"], {})[log["date"].date()] = log

        department_summary = {}

        for employee in employees:
            department = employee["department"]
            weekly_workdays = employee.get("weekly_workdays", 5)
            working_hours = employee.get("working_hours", 8)
            if department not in department_summary:
                department_summary[department] = {
                    "total_working_days": 0,
                    "present_days": 0,
                    "absent_days": 0,
                    "leave_days": 0,
                    "undertime_hours": 0,
                    "overtime_hours": 0,
                    "total_hours_logged": 0
                }

            # Calculate the total working days for this employee in the given month
            start_date = datetime(year, month, 1)
            end_date = datetime(year, month + 1, 1) - timedelta(days=1)
            current_date = start_date

            # Weekly working days are spread across the weeks of the month
            employee_working_days = 0
            while current_date <= end_date:
                if current_date.weekday() < weekly_workdays:
                    employee_working_days += 1
                current_date += timedelta(days=1)

            department_summary[department]["total_working_days"] += employee_working_days

            # Reset current_date for attendance processing
            current_date = start_date
            while current_date <= end_date:
                current_day = current_date.date()
                log = logs_by_date.get(employee["_id"], {}).get(current_day)
                if log:
                    start_time = log.get("start_time")
                    end_time = log.get("end_time")
                    hours_worked = (end_time - start_time).total_seconds() / 3600 if start_time and end_time else 0
                    undertime = hours_worked < working_hours
                    overtime = hours_worked > working_hours

                    if hours_worked >= 0.4 * working_hours:
                        department_summary[department]["present_days"] += 1
                    else:
                        department_summary[department]["absent_days"] += 1

                    if undertime:
                        department_summary[department]["undertime_hours"] += working_hours - hours_worked
                    if overtime:
                        department_summary[department]["overtime_hours"] += hours_worked - working_hours

                    department_summary[department]["total_hours_logged"] += hours_worked
                else:
                    # No log means absent
                    department_summary[department]["absent_days"] += 1

                current_date += timedelta(days=1)

        # Calculate attendance rate for each department
        for department, summary in department_summary.items():
            total_working_days = summary["total_working_days"]
            present_days = summary["present_days"]
            summary["attendance_rate"] = (present_days / total_working_days) * 100 if total_working_days > 0 else 0

        return department_summary

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def calculate_company_metrics(company_id: str, month: int, year: int):
    """Calculate average attendance rate, total hours logged, total overtime hours, and total undertime hours for the company."""
    try:
        department_metrics = await calculate_department_metrics(company_id, month, year)
        
        total_departments = len(department_metrics)
        total_attendance_rate = 0
        total_hours_logged = 0
        total_overtime_hours = 0
        total_undertime_hours = 0

        for metrics in department_metrics.values():
            total_attendance_rate += metrics["attendance_rate"]
            total_hours_logged += metrics["total_hours_logged"]
            total_overtime_hours += metrics["overtime_hours"]
            total_undertime_hours += metrics["undertime_hours"]

        average_attendance_rate = total_attendance_rate / total_departments if total_departments > 0 else 0

        return {
            "average_attendance_rate": average_attendance_rate,
            "total_hours_logged": total_hours_logged,
            "total_overtime_hours": total_overtime_hours,
            "total_undertime_hours": total_undertime_hours
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

async def list_employee_attendance_records(company_id: str, month: int, year: int, department: str = None):
    """List attendance records for employees of the selected company, optionally filtered by department."""
    try:
        start_of_month = datetime(year, month, 1, tzinfo=UTC)
        end_of_month = datetime(year, month, monthrange(year, month)[1], tzinfo=UTC)

        # Fetch employees for the company, optionally filtered by department
        employee_query = {"company_id": company_id, "employment_status": "active"}
        if department:
            employee_query["department"] = {"$regex": f"^{department}$", "$options": "i"}

        employees = await employees_collection.find(employee_query).to_list(length=None)
        if not employees:
            raise ValueError("No employees found for the company.")

        logs_query = {
            "company_id": company_id,
            "date": {"$gte": start_of_month, "$lte": end_of_month}
        }
        logs = await timer_logs_collection.find(logs_query).to_list(length=None)

        logs_by_date = {}
        for log in logs:
            logs_by_date.setdefault(log["employee_id"], {})[log["date"].date()] = log

        employee_records = []

        for employee in employees:
            employee_id = employee["_id"]
            first_name = employee["first_name"]
            last_name = employee["last_name"]
            weekly_workdays = employee.get("weekly_workdays", 5)
            working_hours = employee.get("working_hours", 8)

            total_working_days = 0
            present_days = 0
            absent_days = 0
            leave_days = 0
            undertime_hours = 0
            overtime_hours = 0
            total_hours_logged = 0

            start_date = datetime(year, month, 1)
            end_date = datetime(year, month + 1, 1) - timedelta(days=1)
            current_date = start_date

            while current_date <= end_date:
                if current_date.weekday() < weekly_workdays:
                    total_working_days += 1
                current_date += timedelta(days=1)

            current_date = start_date
            while current_date <= end_date:
                current_day = current_date.date()
                log = logs_by_date.get(employee_id, {}).get(current_day)
                if log:
                    start_time = log.get("start_time")
                    end_time = log.get("end_time")
                    hours_worked = (end_time - start_time).total_seconds() / 3600 if start_time and end_time else 0
                    undertime = hours_worked < working_hours
                    overtime = hours_worked > working_hours

                    if hours_worked >= 0.4 * working_hours:
                        present_days += 1
                    else:
                        absent_days += 1

                    if undertime:
                        undertime_hours += working_hours - hours_worked
                    if overtime:
                        overtime_hours += hours_worked - working_hours

                    total_hours_logged += hours_worked
                else:
                    absent_days += 1

                current_date += timedelta(days=1)

            attendance_percentage = (present_days / total_working_days) * 100 if total_working_days > 0 else 0

            employee_records.append({
                "first_name": first_name,
                "last_name": last_name,
                "attendance_percentage": attendance_percentage,
                "overtime_hours": overtime_hours,
                "undertime_hours": undertime_hours,
                "absences": absent_days,
                "total_hours_logged": total_hours_logged
            })

        return employee_records

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

async def get_monthly_attendance_with_times(employee_id: str, company_id: str, month: int, year: int):
    """Retrieve monthly attendance record with clock-in and clock-out times for a specific employee."""
    try:
        start_date = datetime(year, month, 1, tzinfo=UTC)
        end_date = datetime(year, month, monthrange(year, month)[1], tzinfo=UTC)

        # Fetch approved leaves for the employee
        leaves = await leaves_collection.find({
            "company_id": company_id, 
            "employee_id": employee_id,
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
            "company_id": company_id,
            "employee_id": employee_id,
            "date": {"$gte": start_date, "$lte": end_date}
        }).to_list(length=None)

        logs_by_date = {log["date"].date(): log for log in attendance_logs}

        # Get working hours for the employee
        employee = await employees_collection.find_one({"employee_id": employee_id})
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
                clock_in = None
                clock_out = None
            else:
                log = logs_by_date.get(current_day)
                if log:
                    start_time = log.get("start_time")
                    end_time = log.get("end_time")
                    hours_worked = (end_time - start_time).total_seconds() / 3600 if start_time and end_time else 0
                    overtime = 1 if hours_worked > working_hours else 0
                    undertime = 1 if working_hours > hours_worked >= 0.4 * working_hours else 0
                    absent = 1 if hours_worked < 0.4 * working_hours else 0
                    clock_in = start_time
                    clock_out = end_time

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
                    clock_in = None
                    clock_out = None

            # Add attendance record
            summary.append({
                "date": current_day,
                "attendance_status": attendance_status,
                "hours_worked": round(hours_worked, 2),
                "overtime": overtime,
                "undertime": undertime,
                "absent": absent,
                "clock_in": clock_in,
                "clock_out": clock_out
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

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def calculate_employee_metrics(employee_id: str, company_id: str, month: int, year: int):
    """Calculate attendance rate, total overtime hours, undertime hours, and total absences for an employee."""
    try:
        attendance_data = await get_monthly_attendance_with_times(employee_id, company_id, month, year)
        totals = attendance_data["totals"]

        total_working_days = totals["presents"] + totals["absences"] + totals["undertimes"]
        attendance_rate = (totals["presents"] / total_working_days) * 100 if total_working_days > 0 else 0

        return {
            "attendance_rate": attendance_rate,
            "total_overtime_hours": sum(record["hours_worked"] - 8 for record in attendance_data["attendance_summary"] if record["overtime"]),
            "total_undertime_hours": sum(8 - record["hours_worked"] for record in attendance_data["attendance_summary"] if record["undertime"]),
            "total_absences": totals["absences"]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))