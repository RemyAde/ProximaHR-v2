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
    end_of_current_month = datetime(current_year, current_month, monthrange(current_year, current_month)[1], tzinfo=timezone.utc)

    # Handle previous month logic
    if current_month == 1:
        # If it's January, previous month is December of the previous year
        previous_month = 12
        previous_year = current_year - 1
    else:
        previous_month = current_month - 1
        previous_year = current_year

    start_of_previous_month = datetime(previous_year, previous_month, 1, tzinfo=timezone.utc)
    end_of_previous_month = datetime(previous_year, previous_month, monthrange(previous_year, previous_month)[1], tzinfo=timezone.utc)

    # Function to calculate attendance rate for a given date range
    async def calculate_attendance_rate(start_date, end_date):
        # Fetch all employees for the company
        employees = await employees_collection.find({"company_id": company_id}).to_list(length=None)
        if not employees:
            raise ValueError("No employees found for the company.")

        days_in_range = (end_date - start_date).days + 1

        # Calculate ideal total work hours
        ideal_total_hours = 0
        for employee in employees:
            working_hours = employee.get("working_hours", 0)  # Daily working hours
            weekly_days = employee.get("weekly_workdays", 0)  # Days worked per week
            if working_hours > 0 and weekly_days > 0:
                # Calculate ideal hours for this employee
                ideal_hours = working_hours * weekly_days * (days_in_range / 7)
                ideal_total_hours += ideal_hours

        if ideal_total_hours == 0:
            return 0.0

        # Calculate total hours worked (from attendance logs)
        attendance_logs = await timer_logs_collection.find({
            "company_id": company_id,
            "date": {"$gte": start_date, "$lte": end_date}
        }).to_list(length=None)

        total_hours_worked = sum(log.get("hours_worked", 0) for log in attendance_logs)

        # Calculate attendance rate
        attendance_rate = (total_hours_worked / ideal_total_hours) * 100 if ideal_total_hours > 0 else 0
        return round(attendance_rate, 2)

    # Calculate attendance rates for the current and previous months
    current_month_attendance_rate = await calculate_attendance_rate(start_of_current_month, end_of_current_month)
    previous_month_attendance_rate = await calculate_attendance_rate(start_of_previous_month, end_of_previous_month)

    # Calculate attendance trend
    attendance_trend = current_month_attendance_rate - previous_month_attendance_rate

    return {
        "current_month_attendance_rate": current_month_attendance_rate,
        # "previous_month_attendance_rate": previous_month_attendance_rate,
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
    try:
        # Get the current month and year
        current_date = datetime.now(UTC)  # Ensure UTC for consistency
        year = current_date.year
        month = current_date.month

        # MongoDB aggregation pipeline
        pipeline = [
            {
                "$addFields": {
                    "year": {"$year": "$date"},
                    "month": {"$month": "$date"}
                }
            },
            {
                "$match": {
                    "year": year,
                    "month": month,
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
                    "_id": "$employee_info.department",  # Group by department
                    "total_hours_worked": {"$sum": "$total_hours"},
                    "total_ideal_hours": {
                        "$sum": {
                            "$multiply": [
                                "$employee_info.weekly_workdays",  # Days per week
                                "$employee_info.working_hours",   # Hours per day
                                4.33  # Approximate weeks in a month
                            ]
                        }
                    }
                }
            },
            {
                "$project": {
                    "department": "$_id",  # Assign _id (department name) to department field
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
                    "_id": 0  # Exclude _id
                }
            }
        ]

        # Run aggregation
        cursor = timer_logs_collection.aggregate(pipeline)
        results = await cursor.to_list(length=None)

        # Handle empty results
        if not results:
            return {"message": "No attendance data found for the current month."}

        return results

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


async def calculate_overtime_for_department(month: int, year: int, company_id: str) -> list:
    """
    Calculate total overtime hours, average overtime hours per employee,
    and the employee with the highest overtime hours by department,
    scoped to a specific company.
    """
    pipeline = [
        {
            "$match": {
                "$expr": {
                    "$and": [
                        {"$eq": [{"$month": "$date"}, month]},
                        {"$eq": [{"$year": "$date"}, year]}
                    ]
                },
                "company_id": company_id  # Filter by company_id
            }
        },
        {
            "$lookup": {
                "from": "employees",
                "localField": "employee_id",
                "foreignField": "employee_id",
                "as": "employee_info"
            }
        },
        {
            "$unwind": "$employee_info"
        },
        {
            "$addFields": {
                "overtime_hours": {
                    "$cond": {
                        "if": {"$gt": ["$total_hours", "$employee_info.working_hours"]},
                        "then": {"$subtract": ["$total_hours", "$employee_info.working_hours"]},
                        "else": 0
                    }
                },
                "employee_full_name": {
                    "$concat": [
                        "$employee_info.first_name", 
                        " ", 
                        "$employee_info.last_name"
                    ]
                }
            }
        },
        {
            "$group": {
                "_id": {
                    "department": "$employee_info.department",
                    "employee_id": "$employee_id",
                    "employee_name": "$employee_full_name"
                },
                "total_overtime_hours": {"$sum": "$overtime_hours"}
            }
        },
        {
            "$group": {
                "_id": "$_id.department",
                "total_overtime_hours": {"$sum": "$total_overtime_hours"},
                "average_overtime_hours": {"$avg": "$total_overtime_hours"},
                "max_overtime_employee": {
                    "$max": {
                        "employee_name": "$_id.employee_name",
                        "overtime_hours": "$total_overtime_hours"
                    }
                }
            }
        },
        {
            "$project": {
                "department": "$_id",
                "total_overtime_hours": 1,
                "average_overtime_hours": {"$round": ["$average_overtime_hours", 2]},
                "employee_with_max_overtime": {
                    "name": "$max_overtime_employee.employee_name",
                    "hours": {"$round": ["$max_overtime_employee.overtime_hours", 2]}
                },
                "_id": 0
            }
        }
    ]

    # Use Motor's aggregation and resolve the cursor using to_list()
    cursor = timer_logs_collection.aggregate(pipeline)
    return await cursor.to_list(length=None)


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