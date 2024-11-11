import secrets
import string
from fastapi import APIRouter, Depends, Form, HTTPException
from db import companies_collection, admins_collection, employees_collection
from schemas.admin import CreateAdmin
from models.admins import Admin
from schemas.employee import CreateEmployee
from models.employees import Employee
from utils import hash_password, get_current_user

router = APIRouter()


@router.post("/create-admin")
async def create_admin(admin_obj: CreateAdmin, company_id: str, admin_code: str):
    company = await companies_collection.find_one({"registration_number": company_id})
    if not company:
        raise HTTPException(status_code=400, detail="Company not found")
    
    if company["admin_creation_code"] != admin_code:
        raise HTTPException(status_code=401, detail="Invalid admin creation code")
    
    if len(company.get("admin", [])) >= 1:
        raise HTTPException(status_code=400, detail="Admin limit reached")

    admin_obj_dict = admin_obj.model_dump(exclude_unset=True)
    admin_obj_dict["company_id"] = company_id
    admin_obj_dict["password"] = hash_password(password=admin_obj_dict["password"])

    admin_instance = Admin(**admin_obj_dict)

    await admins_collection.insert_one(admin_instance.model_dump())

    await companies_collection.update_one(
        {"registration_number": company_id},
        {"$push": {"admins": admin_instance.email},
         "$inc": {"staff_size": 1}}
    )

    return {"message": "Admin created successfully"}


def generate_password(length: int = 8) -> str:
    # Define the allowed characters: uppercase, lowercase, and digits
    allowed_characters = string.ascii_letters + string.digits
    
    # Use secrets.choice to securely choose random characters
    password = ''.join(secrets.choice(allowed_characters) for _ in range(length))
    
    return password


@router.post("/create-employee-credentials")
async def create_employee_credentials(employee_request: CreateEmployee, company_id: str, user_and_type: tuple = Depends(get_current_user)):
    user, user_type = user_and_type

    company = await companies_collection.find_one({"registration_number": company_id})
    if not company:
        raise HTTPException(status_code=400, detail="Company not found")
    
    if user["company_id"] != company_id:
        raise HTTPException(status_code=401, detail="You are not authorized to be on this page")
    
    if user_type != "admin":
        raise HTTPException(status_code=401, detail="Unauthorized user!")
    
    existing_employee = await employees_collection.find_one({"employee_id": employee_request.employee_id})
    if existing_employee:
        raise HTTPException(status_code=400, detail="Employee with ID already exits")
    
    employee_pwd = generate_password(8)

    employee_request_dict = employee_request.model_dump(exclude_unset=True)
    employee_request_dict["company_id"] = user["company_id"]
    employee_request_dict["password"] = hash_password(employee_pwd)

    employee_instance = Employee(**employee_request_dict)

    await employees_collection.insert_one(employee_instance.model_dump())

    await companies_collection.update_one({"registration_number": company_id}, {"inc": {"staff_size": 1}})

    data = {"employee_id": employee_instance.employee_id, "password": employee_pwd}

    return {"message": "Employee account created successfully", "data": data}
