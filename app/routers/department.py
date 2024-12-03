from pymongo import ASCENDING
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from db import departments_collection, companies_collection, employees_collection
from models.departments import Department
from schemas.department import DepartmentCreate, DepartmentEdit
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

            hod_details = None
            if department.get("hod"):
                hod_filter = {"employee_id": department["hod"], "company_id": company_id}
                hod = await employees_collection.find_one(hod_filter)
                if hod:
                    hod_details = {
                        "first_name": hod.get("first_name", ""),
                        "last_name": hod.get("last_name", ""),
                    }

            data.append({
                "id": str(department["_id"]),
                "name": department.get("name", ""),
                "staff_size": department.get("staff_size", ""),
                "hod": hod_details,
                "description": department.get("description", "")
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

        # Set staff_size based on the number of staff members
        department_obj_dict["staff_size"] = len(staff_ids)

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
        
            # Update the HOD's position to "department head"
            await employees_collection.update_one(
                {"employee_id": hod_id, "company_id": company_id},
                {"$set": {"position": "department head"}}
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

        return {"message": "Department created successfully"}
    
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"An error occurred: {str(e)}"
        )


@router.get("/department-details")
async def get_department_details(
    company_id: str,
    department_name: str = Query(..., description="Name of the department to fetch details for."),
    user_and_type: tuple = Depends(get_current_user),
):
    """
    Fetches detailed information about a department, including the department's details and 
    the head of department's details such as first name, last name, email, phone number, 
    and work location.
    """
    user, user_type = user_and_type

    if user_type != "admin":
        raise HTTPException(status_code=403, detail="Unauthorized user!")

    # Check if the company exists
    company_filter = {"registration_number": company_id}
    company = await companies_collection.find_one(company_filter)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found.")

    if company.get("registration_number") != user.get("company_id"):
        raise HTTPException(status_code=403, detail="Unauthorized to access this company.")

    # Check if the department exists
    department_filter = {"name": {"$regex": f"^{department_name}$", "$options": "i"}, "company_id": company_id}
    department = await departments_collection.find_one(department_filter)
    if not department:
        raise HTTPException(status_code=404, detail="Department not found.")

    # Get department head details if `hod` field is provided
    hod_details = None
    if department.get("hod"):
        hod_filter = {"employee_id": department["hod"], "company_id": company_id}
        hod = await employees_collection.find_one(hod_filter)
        if hod:
            hod_details = {
                "first_name": hod.get("first_name", ""),
                "last_name": hod.get("last_name", ""),
                "email": hod.get("email", ""),
                "phone_number": hod.get("phone_number", ""),
                "work_location": hod.get("work_location", ""),
            }

    # consumer here hits list employees endpoint and query on department to get employee list

    # Convert ObjectId to string
    department_id = str(department["_id"]) if "_id" in department else None

    # Build and return the department details
    department_details = {
        "department_id": department_id,
        "department_name": department.get("name", ""),
        "description": department.get("description", ""),
        "hod_details": hod_details,  # None if no valid HOD exists
    }

    return {"message": "Department details fetched successfully.", "data": department_details}


@router.put("/{department_id}/edit-department")
async def edit_department(
    company_id: str,
    department_request: DepartmentEdit,
    department_id: str = Path(..., description="ID of the department you want to edit"),
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
        
        # Fetch the department by its ID
        department = await departments_collection.find_one({"_id": ObjectId(department_id)})
        if not department:
            raise HTTPException(status_code=404, detail="Department not found")

        # Initialize the update data dictionary
        update_data = {}

        # Handle HOD (Head of Department) update
        new_hod_id = department_request.hod
        if new_hod_id:
            # Validate if the HOD is a valid employee in the company
            hod_employee = await employees_collection.find_one({"employee_id": new_hod_id, "company_id": company_id})
            if not hod_employee:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail=f"HOD with employee ID {new_hod_id} is not a valid employee of the company"
                )
            
            # Ensure that the HOD is part of the department's staff
            if new_hod_id not in department.get("staffs", []):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail=f"HOD with employee ID {new_hod_id} must also be part of the staff members"
                )
            
            # If there's a current HOD, update their position back to "member"
            current_hod_id = department.get("hod")
            if current_hod_id:
                await employees_collection.update_one(
                    {"employee_id": current_hod_id, "company_id": company_id},
                    {"$set": {"position": "member"}}
                )
            
            # Set the new HOD's position to "department head"
            await employees_collection.update_one(
                {"employee_id": new_hod_id, "company_id": company_id},
                {"$set": {"position": "department head"}}
            )

            # Update the HOD in the department
            update_data["hod"] = new_hod_id

        # Validate addition of new staff members
        staff_ids_to_add = department_request.staffs
        if staff_ids_to_add:
            # Check if each staff member exists and is valid
            for staff_id in staff_ids_to_add:
                staff_employee = await employees_collection.find_one({"employee_id": staff_id, "company_id": company_id})
                if not staff_employee:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST, 
                        detail=f"Staff member with employee ID {staff_id} is not a valid employee of the company"
                    )
            # Add the new staff members
            update_data["staffs"] = list(set(department.get("staffs", [])) | set(staff_ids_to_add))

        # Validate removal of staff members
        staff_ids_to_remove = department_request.remove_staffs
        if staff_ids_to_remove:
            # Check if the employees to be removed are actually in the current staff list
            for staff_id in staff_ids_to_remove:
                if staff_id not in department.get("staffs", []):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST, 
                        detail=f"Staff member with employee ID {staff_id} is not in the department"
                    )
            # Remove the staff members
            update_data["staffs"] = [
                staff for staff in department.get("staffs", []) if staff not in staff_ids_to_remove
            ]

            # Update department field for removed employees
            for staff_id in staff_ids_to_remove:
                await employees_collection.update_one(
                    {"employee_id": staff_id, "company_id": company_id},
                    {"$set": {"department": None}}
                )

        # If `staffs` wasn't explicitly updated, retain the existing value
        if "staffs" not in update_data:
            update_data["staffs"] = department.get("staffs", [])

        # Update the department in the database
        await departments_collection.update_one({"_id": department["_id"]}, {"$set": update_data})

        # Recalculate and update the department's staff size
        new_staff_size = len(update_data["staffs"])
        await departments_collection.update_one({"_id": department["_id"]}, {"$set": {"staff_size": new_staff_size}})
        
        # Return success response
        return {"message": "Department updated successfully", "staff_size": new_staff_size}

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"An error occurred - {e}")
        

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