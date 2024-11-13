from pymongo import ASCENDING

from fastapi import APIRouter, Depends, HTTPException, status 
from db import departments_collection, companies_collection
from models.departments import Department
from schemas.department import DepartmentCreate
from utils import get_current_user
from exceptions import get_user_exception, get_unknown_entity_exception


router = APIRouter()


@router.get("/")
async def list_departments(company_id: str, user_and_type: tuple = Depends(get_current_user)):
    user, user_type = user_and_type
    if user_type != "admin":
        raise get_user_exception()
    
    try:
        company = await companies_collection.find_one({"registration_number": company_id})
        if not company:
            raise get_unknown_entity_exception()

        if company.get("registration_number") != user.get("company_id"):
            raise get_user_exception()
        
        departments = await departments_collection.find({"company_id": company_id}).sort("name", ASCENDING).to_list(length=None)

        return {"departments": departments}
    
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"An error occured - {e}")
    

@router.post("/create-department")
async def create_department(company_id: str, department_request: DepartmentCreate, user_and_type: tuple = Depends(get_current_user)):
    user, user_type = user_and_type
    if user_type != "admin":
        raise get_user_exception()
    
    try:
        company = await companies_collection.find_one({"registration_number": company_id})
        if not company:
            raise get_unknown_entity_exception()

        if company.get("registration_number") != user.get("company_id"):
            raise get_user_exception()
        
        existing_department = await departments_collection.find_one({"name": department_request.name})
        if existing_department:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Department name already exists")
        
        deparment_obj_dict = department_request.model_dump(exclude_unset=True)
        deparment_obj_dict["company_id"] = company_id
        department_instance = Department(**deparment_obj_dict)

        await departments_collection.insert_one(department_instance.model_dump())

        await companies_collection.update_one({"registration_number": company_id}, {"$push": {"departments": department_instance.name}})

        return {"message": "Department created successfully"}
    
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="An error occured - {e}")