from datetime import datetime, timezone
from calendar import monthrange
from bson import ObjectId
from fastapi import HTTPException
from pytz import UTC
from db import timer_logs_collection
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


async def calculate_department_attendance_percentage():
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
                    "month": month
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
                    "department": "$_id",
                    "attendance_percentage": {
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
                    "_id": 0  # Exclude _id field from result
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
    

async def calculate_company_monthly_attendance():
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
                    "year": current_year
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
                    "_id": 0  # Exclude _id field
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

