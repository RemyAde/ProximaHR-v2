from datetime import datetime, timezone
from pymongo.collection import Collection
from typing import List, Dict, Union


async def get_upcoming_events_for_the_month(
    event_collection,  # The MongoDB collection
    company_id: str,   # The ID of the company to filter by
    date_field: str,   # Field name for date (either "date_of_birth" or "employment_date")
    event_type: str    # Type of event ("birthday" or "anniversary")
) -> List[Dict[str, Union[str, str]]]:
    """
    Find users who have upcoming events (birthdays or employment anniversaries) in the current month.
    
    :param event_collection: MongoDB collection of employees
    :param company_id: The ID of the company to filter by
    :param date_field: The field in the employee document (dob or hire_date)
    :param event_type: The type of event to track ("birthday" or "anniversary")
    :return: List of employees with upcoming events
    """
    # Get the current date and the current month
    now = datetime.now(timezone.utc)
    current_month = now.month
    today_day = now.day

    # MongoDB aggregation pipeline
    pipeline = [
        {
            "$match": {
                "company_id": company_id  # Filter employees by company_id
            }
        },
        {
            "$project": {
                "first_name": 1,
                "last_name": 1,
                date_field: 1,  # Use the date_field passed in
                "event_month": { "$month": f"${date_field}" },
                "event_day": { "$dayOfMonth": f"${date_field}" }
            }
        },
        {
            "$match": {
                "event_month": current_month,
                "event_day": { "$gte": today_day }  # Filter events after today
            }
        },
        {
            "$sort": { "event_day": 1 }  # Sort by day within the month
        }
    ]

    # Aggregate the results from MongoDB
    upcoming_events = await event_collection.aggregate(pipeline).to_list(length=None)

    # Format the results based on the event type
    results = []
    for employee in upcoming_events:
        event_data = {
            "name": f"{employee['first_name']} {employee['last_name']}",
            "event_date": employee[date_field].strftime("%Y-%m-%d"),
            "event_type": event_type.capitalize()  # e.g., "Birthday" or "Anniversary"
        }
        
        # Calculate years of service if it's an anniversary
        if event_type.lower() == "anniversary" and date_field == "employment_date":
            hire_date = employee[date_field]
            years_of_service = now.year - hire_date.year
            if (now.month, now.day) < (hire_date.month, hire_date.day):
                years_of_service -= 1  # Adjust if anniversary hasn't occurred this year yet
            event_data["years_with_company"] = years_of_service
        
        results.append(event_data)

    return results