from datetime import datetime, timedelta
from pytz import timezone
from collections import Counter
from db import leaves_collection

UTC = timezone("UTC")


async def get_monthly_leave_distribution(company_id: str):
    now = datetime.now(tz=UTC)
    six_months_ago = now - timedelta(days=180)
    
    # Fetch leaves created in the last 6 months
    leaves_cursor = leaves_collection.find({
        "company_id": company_id,
        "start_date": {"$gte": six_months_ago}
    })
    
    leaves = await leaves_cursor.to_list(length=None)

    if not leaves:
        return []

    # Count leaves per month
    month_counter = Counter()
    for leave in leaves:
        start_date = leave.get("start_date")
        if isinstance(start_date, datetime):
            month_name = start_date.strftime("%B")  # January, February, etc
            month_counter[month_name] += 1

    # Total leaves
    total_leaves = sum(month_counter.values())

    # Prepare percentage data
    distribution = []
    for month, count in month_counter.items():
        percentage = round((count / total_leaves) * 100)
        distribution.append({
            "month": month,
            "percentage": percentage
        })

    # Optional: Sort by month order (January -> December)
    month_order = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]
    distribution.sort(key=lambda x: month_order.index(x["month"]))

    return distribution


async def get_leave_type_counts_for_year(company_id: str, year: int):
    """
    Aggregates total leaves taken for each leave type in the given year for a company.
    """
    start_date = datetime(year, 1, 1, tzinfo=UTC)
    end_date = datetime(year + 1, 1, 1, tzinfo=UTC)
    pipeline = [
        {
            "$match": {
                "company_id": company_id,
                "status": "approved",
                "start_date": {"$gte": start_date, "$lt": end_date}
            }
        },
        {
            "$group": {
                "_id": "$leave_type",
                "total_taken": {"$sum": "$duration"}
            }
        }
    ]
    results = await leaves_collection.aggregate(pipeline).to_list(length=None)
    return {item["_id"]: item["total_taken"] for item in results}