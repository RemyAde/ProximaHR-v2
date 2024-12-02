from pymongo import ASCENDING
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status 
from db import departments_collection, companies_collection, employees_collection
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
        
        data = []
        departments = await departments_collection.find({"company_id": company_id}).sort("name", ASCENDING).to_list(length=None)

        for department in departments:
            data.append({
                "id": str(department["_id"]),
                "name": department.get("name", ""),
                "hod": department.get("hod", ""),
                "staffs": department.get("staffs", ""), #work around either not returning this field or returning full names
                "staff_size": department.get("staff_size", "")
            })

        return {"departments": data}
    
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"An error occured - {e}")
    

@router.post("/create-department", status_code=status.HTTP_201_CREATED)
async def create_department(
    company_id: str, 
    department_request: DepartmentCreate, 
    user_and_type: tuple = Depends(get_current_user)
):
    user, user_type = user_and_type
    if user_type != "admin":
        raise get_user_exception()
    
    try:
        # Verify the company exists
        company = await companies_collection.find_one({"registration_number": company_id})
        if not company:
            raise get_unknown_entity_exception()

        # Ensure the user is part of the company
        if company.get("registration_number") != user.get("company_id"):
            raise get_user_exception()
        
        # Check if the department name (case insensitive) already exists
        existing_department = await departments_collection.find_one({
            "name": {"$regex": f"^{department_request.name}$", "$options": "i"},
            "company_id": company_id
            })
        if existing_department:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Department name already exists")
        
        # Extract department data
        department_obj_dict = department_request.model_dump(exclude_unset=True)
        department_obj_dict["company_id"] = company_id
        hod_id = department_obj_dict.get("hod")
        staff_ids = department_obj_dict.get("staffs", [])

        # Validate HOD
        if hod_id:
            hod_employee = await employees_collection.find_one({"employee_id": hod_id, "company_id": company_id})
            if not hod_employee:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail=f"HOD with employee ID {hod_id} is not a valid employee of the company"
                )
            if hod_id not in staff_ids:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail=f"HOD with employee ID {hod_id} must also be in the list of staff members"
                )

        # Validate all staff IDs
        for staff_id in staff_ids:
            staff_employee = await employees_collection.find_one({"employee_id": staff_id, "company_id": company_id})
            if not staff_employee:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail=f"Staff member with employee ID {staff_id} is not a valid employee of the company"
                )

        # Create and insert department
        department_instance = Department(**department_obj_dict)
        await departments_collection.insert_one(department_instance.model_dump())

        # Update company with the new department
        await companies_collection.update_one(
            {"registration_number": company_id}, 
            {"$push": {"departments": department_instance.name}}
        )

        return {"message": "Department created successfully"}
    
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"An error occurred: {str(e)}"
        )


@router.put("/{department_id}/edit-department")
async def edit_department(department_id: str, company_id: str, department_request: DepartmentCreate, user_and_type: tuple = Depends(get_current_user)):
    user, user_type = user_and_type
    if user_type != "admin":
        raise get_user_exception()
    
    try:
        company = await companies_collection.find_one({"registration_number": company_id})
        if not company:
            raise get_unknown_entity_exception()

        if company.get("registration_number") != user.get("company_id"):
            raise get_user_exception()
        
        department = await departments_collection.find_one({"_id": ObjectId(department_id)})
        
        update_data = {k:v for k, v in department_request.model_dump().items() if v is not None}
        if not update_data:
            raise HTTPException(status_code=400, details="No data provided to update")
        
        data = await departments_collection.update_one({"_id": department["_id"]}, {"$set": update_data})
        if data.matched_count == 0:
            raise HTTPException(status_code=404, detail="Department not found")
        
        return {"message": "Department updated successfully"}
    
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"An error occured - {e}")
        

@router.delete("/{department_id}/delete-department")
async def delete_department(department_id: str, company_id: str, user_and_type: tuple = Depends(get_current_user)):
    user, user_type = user_and_type
    if user_type != "admin":
        raise get_user_exception()
    
    try:
        company = await companies_collection.find_one({"registration_number": company_id})
        if not company:
            raise get_unknown_entity_exception()

        if company.get("registration_number") != user.get("company_id"):
            raise get_user_exception()
        
        department = await departments_collection.find_one({"_id": ObjectId(department_id)})
        if not department:
            raise get_unknown_entity_exception()
        
        await departments_collection.delete_one({"_id": department["_id"]})
        
        return {"message": "Department deleted successfully"}
    
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"An error occured - {e}")