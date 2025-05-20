from datetime import datetime, timedelta, timezone
from calendar import monthrange
from bson import ObjectId
from fastapi import HTTPException
from pytz import UTC
from db import timer_logs_collection, leaves_collection, employees_collection
from pymongo.errors import PyMongoError


def serialize_objectid(data):
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                serialize_objectid(item)
    elif isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, ObjectId):
                data[key] = str(value)
            elif isinstance(value, (dict, list)):
                serialize_objectid(value)

async def calculate_attendance_trend(company_id, employees_collection, timer_logs_collection):
    today = datetime.now(timezone.utc)
    current_month = today.month
    current_year = today.year

    # Define date ranges for the current and previous months
    start_of_current_month = datetime(current_year, current_month, 1, tzinfo=timezone.utc)
    end_of_current_month = datetime(current_year, current_month, monthrange(current_year, current_month)[1], 23, 59, 59, tzinfo=timezone.utc)

    if current_month == 1:
        previous_month = 12
        previous_year = current_year - 1
    else:
        previous_month = current_month - 1
        previous_year = current_year

    start_of_previous_month = datetime(previous_year, previous_month, 1, tzinfo=timezone.utc)
    end_of_previous_month = datetime(previous_year, previous_month, monthrange(previous_year, previous_month)[1], 23, 59, 59, tzinfo=timezone.utc)

    async def get_total_hours_and_ideal(company_id, employees_collection, timer_logs_collection, start_date, end_date):
        # Fetch all active employees for the company
        employees = await employees_collection.find({"company_id": company_id, "employment_status": "active"}).to_list(length=None)
        if not employees:
            return 0.0, 0.0
        # Build a set of employee_ids
        employee_ids = [emp["employee_id"] for emp in employees]
        # Fetch all timer logs for the period for these employees
        logs = await timer_logs_collection.find({
            "company_id": company_id,
            "employee_id": {"$in": employee_ids},
            "date": {"$gte": start_date, "$lte": end_date}
        }).to_list(length=None)
        # Sum total hours worked
        total_hours_worked = sum(log.get("total_hours", log.get("hours_worked", 0)) for log in logs)
        # Calculate ideal total work hours for all employees
        days_in_range = (end_date.date() - start_date.date()).days + 1
        ideal_total_hours = 0
        for emp in employees:
            working_hours = emp.get("working_hours", 8)
            weekly_days = emp.get("weekly_workdays", 5)
            # Count number of weekdays in range for this employee
            weekday_count = 0
            for i in range(days_in_range):
                d = start_date.date() + timedelta(days=i)
                if d.weekday() < weekly_days:
                    weekday_count += 1
            ideal_total_hours += weekday_count * working_hours
        return total_hours_worked, ideal_total_hours

    # Calculate for current month
    current_total, current_ideal = await get_total_hours_and_ideal(company_id, employees_collection, timer_logs_collection, start_of_current_month, end_of_current_month)
    current_month_attendance_rate = (current_total / current_ideal) * 100 if current_ideal > 0 else 0.0
    # Calculate for previous month
    prev_total, prev_ideal = await get_total_hours_and_ideal(company_id, employees_collection, timer_logs_collection, start_of_previous_month, end_of_previous_month)
    previous_month_attendance_rate = (prev_total / prev_ideal) * 100 if prev_ideal > 0 else 0.0
    # Calculate attendance trend
    attendance_trend = current_month_attendance_rate - previous_month_attendance_rate
    return {
        "current_month_attendance_rate": round(current_month_attendance_rate, 2),
        "previous_month_attendance_rate": round(previous_month_attendance_rate, 2),
        "attendance_trend": round(attendance_trend, 2)
    }


async def calculate_leave_utilization_trend(company_id, employees_collection, leave_logs_collection):
    today = datetime.now(timezone.utc)
    current_month = today.month
    current_year = today.year

    # Define date ranges for the current and previous months
    start_of_current_month = datetime(current_year, current_month, 1, tzinfo=timezone.utc)
    end_of_current_month = datetime(current_year, current_month, monthrange(current_year, current_month)[1], tzinfo=timezone.utc)

    if current_month == 1:
        previous_month = 12
        previous_year = current_year - 1
    else:
        previous_month = current_month - 1
        previous_year = current_year

    start_of_previous_month = datetime(previous_year, previous_month, 1, tzinfo=timezone.utc)
    end_of_previous_month = datetime(previous_year, previous_month, monthrange(previous_year, previous_month)[1], tzinfo=timezone.utc)

    # Function to calculate leave utilization for a given date range
    async def calculate_leave_utilization(start_date, end_date):
        # Fetch all employees for the company
        employees = await employees_collection.find({"company_id": company_id}).to_list(length=None)
        if not employees:
            raise ValueError("No employees found for the company.")

        # Calculate total allocated leave for all employees
        total_allocated_leave = sum(employee.get("annual_leave_days", 0) for employee in employees)
        if total_allocated_leave == 0:
            return 0.0

        # Fetch leave logs for the given date range
        leave_logs = await leave_logs_collection.find({
            "company_id": company_id,
            "start_date": {"$gte": start_date},
            "end_date": {"$lte": end_date}
        }).to_list(length=None)

        # Calculate total leave days used
        total_used_leave = 0
        for log in leave_logs:
            start_date = log.get("start_date")
            end_date = log.get("end_date")
            if start_date and end_date:
                leave_days = (end_date - start_date).days + 1  # Include both start and end dates
                total_used_leave += leave_days

        # Calculate leave utilization
        leave_utilization = (total_used_leave / total_allocated_leave) * 100
        return round(leave_utilization, 2)

    # Calculate leave utilization for the current and previous months
    current_month_leave_utilization = await calculate_leave_utilization(start_of_current_month, end_of_current_month)
    previous_month_leave_utilization = await calculate_leave_utilization(start_of_previous_month, end_of_previous_month)

    # Calculate leave utilization trend
    leave_trend = current_month_leave_utilization - previous_month_leave_utilization

    return {
        "current_month_leave_utilization": current_month_leave_utilization,
        "previous_month_leave_utilization": previous_month_leave_utilization,
        "leave_trend": round(leave_trend, 2)
    }

async def calculate_payroll_trend(current_cost: float, previous_cost: float) -> float:
    if previous_cost == 0:  # Avoid division by zero
        return 100
    trend = (current_cost / previous_cost) * 100
    return trend


async def calculate_department_attendance_percentage(company_id: str):
    """
    For each department, calculate the average of individual employee attendance rates for the current month.
    Attendance rate per employee = present_days / (working_days - leave_days) * 100
    Department attendance rate = average of employee attendance rates in that department.
    """
    try:
        current_date = datetime.now(UTC)
        year = current_date.year
        month = current_date.month
        start_of_month = datetime(year, month, 1, tzinfo=UTC)
        end_of_month = datetime(year, month, monthrange(year, month)[1], tzinfo=UTC)
        today = current_date.date()

        # Fetch all employees for the company
        employees = await employees_collection.find({"company_id": company_id, "employment_status": "active"}).to_list(length=None)
        if not employees:
            return []

        # Fetch all departments for mapping
        departments = await employees_collection.database["departments"].find({"company_id": company_id}).to_list(length=None)
        id_to_name = {str(dept["_id"]): dept["name"] for dept in departments}
        name_to_name = {dept["name"]: dept["name"] for dept in departments}

        # Fetch all approved leaves for the month
        leaves = await leaves_collection.find({
            "company_id": company_id,
            "status": "approved",
            "start_date": {"$lte": end_of_month},
            "end_date": {"$gte": start_of_month}
        }).to_list(length=None)
        # Map employee_id to set of leave dates
        employee_leave_dates = {}
        for leave in leaves:
            emp_id = leave["employee_id"]
            leave_start = leave["start_date"].date()
            leave_end = leave["end_date"].date()
            dates = set((leave_start + timedelta(days=i)) for i in range((leave_end - leave_start).days + 1))
            employee_leave_dates.setdefault(emp_id, set()).update(dates)

        # Fetch all timer logs for the month
        logs = await timer_logs_collection.find({
            "company_id": company_id,
            "date": {"$gte": start_of_month, "$lte": end_of_month}
        }).to_list(length=None)
        # Map employee_id to logs by date
        logs_by_employee = {}
        for log in logs:
            emp_id = log["employee_id"]
            log_date = log["date"].date()
            logs_by_employee.setdefault(emp_id, {})[log_date] = log

        # Group employees by department
        department_employees = {}
        for emp in employees:
            raw_dept = emp.get("department")
            dept_name = (
                id_to_name.get(str(raw_dept)) or
                name_to_name.get(str(raw_dept)) or
                str(raw_dept) or
                "Unknown Department"
            )
            department_employees.setdefault(dept_name, []).append(emp)

        department_results = []
        for dept_name, emp_list in department_employees.items():
            emp_rates = []
            for emp in emp_list:
                emp_id = emp["employee_id"]
                weekly_workdays = int(emp.get("weekly_workdays", 5))
                working_hours = float(emp.get("working_hours", 8))
                # Calculate working days for this employee in the month (weekdays only)
                start_date = datetime(year, month, 1, tzinfo=UTC)
                end_date = datetime(year, month, monthrange(year, month)[1], tzinfo=UTC)
                total_working_days = 0
                dates_in_month = []
                current_date = start_date
                while current_date <= end_date:
                    if current_date.weekday() < weekly_workdays:
                        # If current month, only process up to today
                        if year == today.year and month == today.month and current_date.date() > today:
                            break
                        total_working_days += 1
                        dates_in_month.append(current_date.date())
                    current_date += timedelta(days=1)
                leave_dates = employee_leave_dates.get(emp_id, set())
                present_days = 0
                leave_days = 0
                for day in dates_in_month:
                    if day in leave_dates:
                        leave_days += 1
                        continue
                    log = logs_by_employee.get(emp_id, {}).get(day)
                    if log:
                        start_time = log.get("start_time")
                        end_time = log.get("end_time")
                        hours_worked = (end_time - start_time).total_seconds() / 3600 if start_time and end_time else 0.0
                        if hours_worked >= 0.9 * working_hours:
                            present_days += 1
                effective_days = total_working_days - leave_days
                attendance_rate = (present_days / effective_days) * 100 if effective_days > 0 else 0
                emp_rates.append(attendance_rate)
            dept_attendance_rate = round(sum(emp_rates) / len(emp_rates), 2) if emp_rates else 0.0
            department_results.append({
                "department": dept_name,
                "attendance_percentage": dept_attendance_rate
            })
        return department_results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

async def calculate_company_monthly_attendance(company_id: str):
    try:
        # Get the current year
        current_year = datetime.now(UTC).year

        # Aggregation pipeline
        pipeline = [
            {
                "$addFields": {
                    "year": {"$year": "$date"},
                    "month": {"$month": "$date"}
                }
            },
            {
                "$match": {
                    "year": current_year,
                    "company_id": company_id  # Filter by company_id
                }
            },
            {
                "$lookup": {
                    "from": "employees",  # Employee collection
                    "localField": "employee_id",  # Match employee_id in timer_logs
                    "foreignField": "employee_id",  # Match employee_id in employees
                    "as": "employee_info"
                }
            },
            {
                "$unwind": "$employee_info"  # Unwind joined employee_info array
            },
            {
                "$group": {
                    "_id": {"month": "$month"},  # Group by month
                    "total_hours_worked": {"$sum": "$total_hours"},
                    "total_ideal_hours": {
                        "$sum": {
                            "$multiply": [
                                "$employee_info.weekly_workdays",  # Weekly workdays
                                "$employee_info.working_hours",   # Daily work hours
                                4.33  # Approximate weeks in a month
                            ]
                        }
                    }
                }
            },
            {
                "$project": {
                    "month": "$_id.month",
                    "attendance_percentage": {
                        "$round": [
                            {
                                "$multiply": [
                                    {
                                        "$cond": {
                                            "if": {"$eq": ["$total_ideal_hours", 0]},
                                            "then": 0,
                                            "else": {
                                                "$divide": ["$total_hours_worked", "$total_ideal_hours"]
                                            }
                                        }
                                    },
                                    100
                                ]
                            },
                            2  # Round to 2 decimal places
                        ]
                    },
                    "_id": 0
                }
            },
            {
                "$sort": {"month": 1}  # Sort by month in ascending order
            }
        ]

        # Run aggregation
        cursor = timer_logs_collection.aggregate(pipeline)
        results = await cursor.to_list(length=None)

        # Handle empty results
        if not results:
            return {"message": "No attendance data found for the current year."}

        return results

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def calculate_overtime_for_department(month: int, year: int, company_id: str) -> dict:
    """
    Calculate total overtime hours, average overtime hours per employee,
    and the employee with the highest overtime hours by department,
    using per-day logic consistent with calculate_employee_metrics.
    """
    try:
        # Fetch all employees for the company
        employees = await employees_collection.find({"company_id": company_id, "employment_status": "active"}).to_list(length=None)
        if not employees:
            return {"message": "No employees found for the company.", "data": []}

        # Fetch all departments for mapping
        departments = await employees_collection.database["departments"].find({"company_id": company_id}).to_list(length=None)
        id_to_name = {str(dept["_id"]): dept["name"] for dept in departments}
        name_to_name = {dept["name"]: dept["name"] for dept in departments}

        # Fetch all timer logs for the month
        start_of_month = datetime(year, month, 1, tzinfo=UTC)
        end_of_month = datetime(year, month, monthrange(year, month)[1], tzinfo=UTC)
        logs = await timer_logs_collection.find({
            "company_id": company_id,
            "date": {"$gte": start_of_month, "$lte": end_of_month}
        }).to_list(length=None)
        # Map employee_id to logs by date
        logs_by_employee = {}
        for log in logs:
            emp_id = log["employee_id"]
            log_date = log["date"].date()
            logs_by_employee.setdefault(emp_id, {})[log_date] = log

        # Aggregate overtime per employee and department
        department_data = {}
        for emp in employees:
            emp_id = emp["employee_id"]
            raw_dept = emp.get("department")
            dept_name = (
                id_to_name.get(str(raw_dept)) or
                name_to_name.get(str(raw_dept)) or
                str(raw_dept) or
                "Unknown Department"
            )
            working_hours = float(emp.get("working_hours", 8))
            # For each day in the month, sum overtime
            overtime_total = 0.0
            for log in logs_by_employee.get(emp_id, {}).values():
                hours_worked = log.get("total_hours")
                if hours_worked is None:
                    # fallback to hours_worked if present
                    hours_worked = log.get("hours_worked", 0)
                if hours_worked > working_hours:
                    overtime_total += hours_worked - working_hours
            if dept_name not in department_data:
                department_data[dept_name] = {
                    "employees": [],
                    "total_overtime_hours": 0.0
                }
            department_data[dept_name]["employees"].append({
                "employee_id": emp_id,
                "employee_name": f"{emp.get('first_name', '')} {emp.get('last_name', '')}",
                "overtime_hours": round(overtime_total, 2)
            })
            department_data[dept_name]["total_overtime_hours"] += overtime_total

        # Prepare result: for each department, total, average, and max overtime
        results = []
        for dept_name, data in department_data.items():
            employees = data["employees"]
            total = round(data["total_overtime_hours"], 2)
            avg = round(total / len(employees), 2) if employees else 0.0
            max_emp = max(employees, key=lambda e: e["overtime_hours"], default=None)
            results.append({
                "department": dept_name,
                "total_overtime_hours": total,
                "average_overtime_hours": avg,
                "employee_with_max_overtime": {
                    "name": max_emp["employee_name"] if max_emp else None,
                    "hours": max_emp["overtime_hours"] if max_emp else 0.0
                }
            })
        if not results:
            return {"message": "No overtime data found for the given month and year.", "data": []}
        return {"message": "Success", "data": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def fetch_approved_leaves(month: int, year: int, company_id: str):
    """Fetch approved leaves for the given month and year."""
    start_of_month = datetime(year, month, 1)
    next_month = month % 12 + 1
    next_year = year if month < 12 else year + 1
    start_of_next_month = datetime(next_year, next_month, 1)

    # Query approved leaves within the range
    query = {
        "company_id": company_id,
        "status": "approved",
        "$or": [
            {"start_date": {"$gte": start_of_month, "$lt": start_of_next_month}},
            {"end_date": {"$gte": start_of_month, "$lt": start_of_next_month}}
        ]
    }

    leaves = await leaves_collection.find(query).to_list(length=None)
    return leaves

async def calculate_attendance_for_department(month: int, year: int, company_id: str, work_threshold: float = 0.4) -> dict:
    """Calculate attendance metrics for each department with updated logic."""
    # Fetch all approved leaves for the month and year
    leaves = await fetch_approved_leaves(month, year, company_id)

    # Process leave dates into a set for quick lookup
    leave_dates = set()
    for leave in leaves:
        start_date = max(leave["start_date"], datetime(year, month, 1))
        end_date = min(leave["end_date"], datetime(year, month + 1, 1) - timedelta(days=1))
        leave_dates.update([start_date.date() + timedelta(days=i) for i in range((end_date - start_date).days + 1)])

    # Fetch attendance logs for the month and company
    logs_query = {
        "company_id": company_id,
        "$expr": {
            "$and": [
                {"$eq": [{"$month": "$date"}, month]},
                {"$eq": [{"$year": "$date"}, year]}
            ]
        }
    }
    logs = await timer_logs_collection.find(logs_query).to_list(length=None)

    # Group logs by employee and date
    logs_by_date = {}
    for log in logs:
        logs_by_date.setdefault(log["employee_id"], {})[log["date"].date()] = log

    # Fetch all employees for the company
    employees = await employees_collection.find({"company_id": company_id}).to_list(length=None)

    department_summary = {}

    # Rest of the function remains the same...
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
                "undertime_count": 0,
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
            is_leave_day = current_day in leave_dates

            if is_leave_day:
                attendance_status = "on_leave"
                department_summary[department]["leave_days"] += 1
            else:
                log = logs_by_date.get(employee["_id"], {}).get(current_day)
                if log:
                    start_time = log.get("start_time")
                    end_time = log.get("end_time")
                    hours_worked = (end_time - start_time).total_seconds() / 3600 if start_time and end_time else 0
                    undertime = hours_worked < working_hours

                    if hours_worked >= work_threshold * working_hours:
                        attendance_status = "present"
                        department_summary[department]["present_days"] += 1
                    elif undertime:
                        attendance_status = "undertime"
                        department_summary[department]["undertime_count"] += 1
                    else:
                        attendance_status = "absent"
                        department_summary[department]["absent_days"] += 1
                else:
                    # No log means absent
                    attendance_status = "absent"
                    department_summary[department]["absent_days"] += 1

            current_date += timedelta(days=1)

    return department_summary


async def calculate_average_working_hours(company_id: str, timer_logs_collection) -> float:
    """Calculate average working hours from timer logs for current month."""
    try:
        current_date = datetime.now(UTC)
        start_of_month = datetime(current_date.year, current_date.month, 1, tzinfo=UTC)
        
        pipeline = [
            {
                "$match": {
                    "company_id": company_id,
                    "date": {
                        "$gte": start_of_month,
                        "$lte": current_date
                    }
                }
            },
            {
                "$group": {
                    "_id": None,
                    "avg_hours": {
                        "$avg": "$total_hours"
                    }
                }
            }
        ]
        
        result = await timer_logs_collection.aggregate(pipeline).to_list(length=1)
        return result[0]["avg_hours"] if result else 0.0
        
    except Exception:
        return 0.0