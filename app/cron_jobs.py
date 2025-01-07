from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timezone

# Import your database collections and helper functions
from db import employees_collection, companies_collection, payroll_collection

# Create a shared scheduler instance
scheduler = AsyncIOScheduler()

async def revert_suspensions():
    now = datetime.now(timezone.utc)
    try:
        async for employee in employees_collection.find({"employment_status": "suspended"}):
            if "suspension" in employee:
                end_date = employee["suspension"].get("end_date")
                if end_date and datetime.strptime(end_date, "%Y-%m-%dT%H:%M:%SZ") <= now:
                    await employees_collection.update_one(
                        {"employee_id": employee["employee_id"]},
                        {"$set": {"employment_status": "active"}, "$unset": {"suspension": ""}}
                    )
        print("Suspensions reverted successfully")
    except Exception as e:
        print(f"Error during suspension reversion: {e}")

# Add revert suspensions job to scheduler
scheduler.add_job(
    revert_suspensions,
    "interval",
    hours=72,  # Run every hour
)

async def calculate_yearly_payroll():
    now = datetime.now(timezone.utc)
    current_year = now.year

    try:
        companies = await companies_collection.find().to_list(length=None)
        for company in companies:
            company_id = company["_id"]
            payroll_cost_cursor = employees_collection.aggregate([
                {
                    "$match": {
                        "company_id": company_id,
                        "employment_status": {"$ne": "inactive"}
                    }
                },
                {
                    "$group": {
                        "_id": None,
                        "total_payroll_cost": {
                            "$sum": {
                                "$add": [
                                    "$base_salary",
                                    {"$ifNull": ["$overtime_hours_allowance", 0]},
                                    {"$ifNull": ["$housing_allowance", 0]},
                                    {"$ifNull": ["$transport_allowance", 0]},
                                    {"$ifNull": ["$medical_allowance", 0]},
                                    {"$ifNull": ["$company_match", 0]}
                                ]
                            }
                        }
                    }
                }
            ])
            payroll_cost_result = await payroll_cost_cursor.to_list(length=1)
            payroll_cost = payroll_cost_result[0]["total_payroll_cost"] if payroll_cost_result else 0

            await payroll_collection.update_one(
                {"company_id": company_id, "year": current_year},
                {"$set": {"total_payroll_cost": payroll_cost}},
                upsert=True
            )
            print(f"Yearly payroll for company {company_id} in {current_year}: {payroll_cost}")

    except Exception as e:
        print(f"Error during yearly payroll calculation: {e}")

# Add calculate yearly payroll job to scheduler
scheduler.add_job(
    calculate_yearly_payroll,
    "cron",
    day=31,
    month=12,
    hour=23,
    minute=59,  # Run on the last minute of the year
    timezone="UTC"
)