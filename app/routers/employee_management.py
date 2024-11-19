from datetime import datetime
from fastapi import APIRouter, Depends, status, HTTPException
from db import employees_collection, companies_collection
from utils import get_current_user
from exceptions import get_unknown_entity_exception, get_user_exception


router = APIRouter()


@router.get("/all-employees")
async def get_all_employees(company_id: str, page: int = 1, page_size: int = 10, user_and_type: tuple=Depends(get_current_user)):

    user, user_type = user_and_type
    if user_type != "admin":
        raise get_user_exception()
    
    try: 
        data = []

        company = await companies_collection.find_one({"registration_number": company_id})
        if not company:
            raise get_unknown_entity_exception()
        
        if company.get("registration_number") != user.get("company_id"):
            raise get_user_exception()
        
        data.append({
            "staff_size": company.get("staff_size", "")
        })
        
        if page < 1:
            page = 1

        skip = (page - 1) * page_size
        
        employees_list = await employees_collection.find({"company_id": company_id}).sort("employment_date", 1).skip(skip).limit(page_size).to_list(length=page_size)
        
        for employee in employees_list:
            data.append({
                "company_id": employee.get("company_id", ""),
                "profile_image": employee.get("profile_image", ""),
                "employee_id": employee["employee_id"],
                "name": f"{employee['first_name']} {employee['last_name']}",
                "job_title": employee.get("job_title", ""),
                "department": employee.get("department", ""),
                "employment_status": employee.get("employment_status", ""),
            })

        return {"data": data}
    
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"An exception has occured - {e}")


@router.post("/suspend-employee/{employee_id}")
async def suspend_employee(
    company_id: str,
    employee_id: str,
    suspension_data: dict,
    user_and_type: tuple = Depends(get_current_user)
):
    user, user_type = user_and_type
    
    # Check if the user is authorized
    if user_type != "admin":
        raise HTTPException(status_code=403, detail="Unauthorized user!")
    
    if company_id != user.get("company_id"):
        raise get_user_exception()
    
    # Find the employee
    employee = await employees_collection.find_one({"employee_id": employee_id})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    # Update suspension details
    suspension_data["start_date"] = datetime.strptime(suspension_data["start_date"], "%Y-%m-%d")
    suspension_data["end_date"] = datetime.strptime(suspension_data["end_date"], "%Y-%m-%d")
    if suspension_data["start_date"] >= suspension_data["end_date"]:
        raise HTTPException(status_code=400, detail="End date must be after start date")
    
    await employees_collection.update_one(
        {"employee_id": employee_id},
        {
            "$set": {
                "employment_status": "suspended",
                "suspension": suspension_data
            }
        }
    )
    
    return {"message": "Employee successfully suspended"}