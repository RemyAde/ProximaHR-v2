from datetime import datetime
from typing import Optional
from pymongo.errors import PyMongoError
from fastapi import APIRouter, Depends, status, HTTPException
from schemas.employee import CreateEmployee
from models.employees import Employee
from db import client, employees_collection, companies_collection, departments_collection
from utils import get_current_user, generate_password, hash_password
from exceptions import get_unknown_entity_exception, get_user_exception


router = APIRouter()


@router.get("/all-employees")
async def list_employees(
    company_id: str,
    page: int = 1,
    page_size: int = 10,
    department_name: Optional[str] = None,  # Optional department name query parameter
    user_and_type: tuple = Depends(get_current_user),
):
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

        # Build the query filter dynamically
        query_filter = {
            "company_id": company_id,
            "employment_status": {"$ne": "inactive"}  # Exclude users with employment_status as 'inactive'
        }
        
        if department_name:  # Add department filter if provided
            query_filter["department"] = department_name

        # Fetch filtered employees
        employees_list = await employees_collection.find(query_filter).sort("employment_date", 1).skip(skip).limit(page_size).to_list(length=page_size)
        
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"An exception has occurred - {e}")


@router.get("/employee/{employee_id}")
async def get_employee_details(
    employee_id: str, 
    company_id: str,
    user_and_type: tuple = Depends(get_current_user)
):
    user, user_type = user_and_type

    company = await companies_collection.find_one({"registration_number": company_id})
    if not company:
        raise get_unknown_entity_exception()

    if company.get("registration_number") != user.get("company_id"):
        raise get_user_exception()

    if user_type not in ["admin", "hr"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="You are not authorized to view employee details."
        )
    
    # Fetch employee from database
    employee = await employees_collection.find_one({"employee_id": employee_id}) #ensure only company employee is accessible
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Employee not found."
        )
    
    # Serialize and omit fields
    serialized_employee = Employee(**employee).model_dump(exclude={"company_id", "password", "date_created"})

    return {"data": serialized_employee}


@router.post("/create-employee-profile")
async def create_employee_profile(employee_request: CreateEmployee, company_id: str, user_and_type: tuple = Depends(get_current_user)):
    user, user_type = user_and_type

    company = await companies_collection.find_one({"registration_number": company_id})
    if not company:
        raise HTTPException(status_code=400, detail="Company not found")
    
    if user["company_id"] != company_id:
        raise HTTPException(status_code=401, detail="You are not authorized to be on this page")
    
    if user_type != "admin":
        raise HTTPException(status_code=401, detail="Unauthorized user!")
    
    existing_employee = await employees_collection.find_one({
        "$or": [
            {"employee_id": employee_request.employee_id},
            {"email": employee_request.email}
        ]
    })
    if existing_employee:
        raise HTTPException(status_code=400, detail="Employee already exists")
    
    employee_pwd = generate_password(8)

    # Create the employee data
    employee_request_dict = employee_request.model_dump(exclude_unset=True)
    employee_request_dict["company_id"] = user["company_id"]
    employee_request_dict["password"] = hash_password(employee_pwd)
    employee_request_dict["date_of_birth"] = datetime.combine(employee_request.date_of_birth, datetime.min.time())

    # Start a session and transaction
    async with await client.start_session() as session:
        async with session.start_transaction():
            try:
                # Insert the employee
                employee_instance = Employee(**employee_request_dict)
                await employees_collection.insert_one(employee_instance.model_dump(), session=session)

                # Validate and update the department
                if employee_instance.department:
                    updated_department = await departments_collection.update_one(
                        {"name": employee_instance.department},  # Use department name or ID
                        {
                            "$push": {"staffs": employee_instance.employee_id},
                            "$inc": {"staff_size": 1}
                        },
                        session=session,
                        upsert=False
                    )
                    if updated_department.matched_count == 0:
                        raise HTTPException(status_code=404, detail="Department not found")
                
                # Increment the company's staff size
                await companies_collection.update_one(
                    {"registration_number": company_id}, 
                    {"$inc": {"staff_size": 1}},
                    session=session
                )

                # Commit the transaction
                await session.commit_transaction()

            except PyMongoError as e:
                # Abort the transaction if an error occurs
                await session.abort_transaction()
                raise HTTPException(status_code=500, detail=f"Transaction failed: {str(e)}")
    
    # Return success response
    data = {"employee_id": employee_instance.employee_id, "password": employee_pwd}
    return {"message": "Employee account created successfully", "data": data}


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


@router.post("/deactivate-employee/{employee_id}")
async def deactivate_employee(
    company_id: str,
    employee_id: str,
    deactivation_data: dict,
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
    
    await employees_collection.update_one(
        {"employee_id": employee_id},
        {
            "$set": {
                "employment_status": "inactive",
                "deactivation": deactivation_data
            }
        }
    )
    
    return {"message": "Employee successfully deactivated"}