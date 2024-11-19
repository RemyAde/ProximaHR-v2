from fastapi import APIRouter, HTTPException, Depends, status
from db import companies_collection, admins_collection, employees_collection
from utils import get_current_user
from exceptions import get_user_exception, get_unknown_entity_exception
from dashboard_utils import get_upcoming_events_for_the_month

router = APIRouter()


# First Pane

@router.get("/first-section")
async def get_company_info(company_id, user_and_type: tuple = Depends(get_current_user)):
    user, user_type = user_and_type

    if user_type != "admin":
        raise get_user_exception()
    
    try:
        data = {}
        company = await companies_collection.find_one({"registration_numnber": company_id})
        if not company:
            raise get_unknown_entity_exception()
        
        if str(company.get("registration_number")) != str(user["company_id"]):
            raise get_user_exception()
        
        # query to get pending leave request and do the same
        # query for attendance overview
        
        staff_size = company.get("staff_size")
        
        data.update({
            "total_employees": staff_size
        })

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"an error occured - {e}")


@router.get("/events")
async def get_events(company_id:str, user_and_type: tuple = Depends(get_current_user)):
    data = {}

    company = await companies_collection.find_one({"registration_number": company_id})
    if not company:
        raise get_unknown_entity_exception()
    
    user, user_type = user_and_type
    if user_type != "admin":
        raise get_user_exception()
    
    if str(company.get("registration_number")) != str(user.get("company_id")):
        raise get_user_exception()
    
    upcoming_birthdays = await get_upcoming_events_for_the_month(event_collection=employees_collection, company_id=company_id, date_field="date_of_birth", event_type="birthday")
    birthday_count = len(upcoming_birthdays)

    data.update(
        {"birthday_count": birthday_count, "birthdays": upcoming_birthdays}
    )

    upcoming_anniversaries = await get_upcoming_events_for_the_month(event_collection=employees_collection, company_id=company_id, date_field="employment_date", event_type="anniversary")
    anniversary_count = len(upcoming_anniversaries)

    total_event_count = birthday_count + anniversary_count

    data.update(
        {"anniversary_count": anniversary_count,
         "anniversaries": upcoming_anniversaries,
         "total_event_count": total_event_count}
    )
    
    return data
