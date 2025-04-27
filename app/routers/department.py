from typing import Optional
from pymongo import ASCENDING
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from db import departments_collection, companies_collection, employees_collection, admins_collection
from models.departments import Department
from schemas.department import DepartmentCreate, DepartmentEdit
from utils.app_utils import get_current_user
from utils.activity_utils import log_admin_activity
from exceptions import get_user_exception, get_unknown_entity_exception


router = APIRouter()


@router.get("/")
async def list_departments(department_name: Optional[str] = Query(None, description="Search department by name"), 
                           user_and_type: tuple = Depends(get_current_user)):
    """
    Retrieve a list of all departments for a given company.
    This async function fetches all departments belonging to a company, including details about
    their Heads of Department (HOD) if available. Only admin users can access this endpoint.
    Args:
        company_id (str): The registration number of the company
        user_and_type (tuple): A tuple containing user information and user type, obtained from get_current_user dependency
    Returns:
        dict: A dictionary containing list of departments with their details:
            - departments: List of dictionaries containing:
                - id (str): Department's unique identifier
                - name (str): Name of the department
                - staff_size (str): Number of staff in the department
                - hod (dict|None): Head of Department details if exists:
                    - first_name (str): HOD's first name
                    - last_name (str): HOD's last name
                - description (str): Department description
    Raises:
        HTTPException: If user is not admin, company doesn't exist, or any other error occurs
        UserException: If user does not have permission to access company data
        UnknownEntityException: If company is not found
    """

    user, user_type = user_and_type
    if user_type != "admin":
        raise HTTPException(status_code=403, detail="Unauthorized user!")
    
    company_id = user.get("company_id")
    
    try:
        company = await companies_collection.find_one({"registration_number": company_id})
        if not company:
            raise get_unknown_entity_exception()
        
        data = []
        query_filter = {"company_id": company_id}
        if department_name:
            query_filter["name"] = {"$regex": f"^{department_name}", "$options": "i"}
        departments = await departments_collection.find(query_filter).sort("name", ASCENDING).to_list(length=None)

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
    department_request: DepartmentCreate, 
    user_and_type: tuple = Depends(get_current_user)
):  
    """
    Create a new department within a company.
    This async function creates a department, validates the HOD and staff members,
    and ensures proper permissions and data consistency.
    Args:
        company_id (str): The registration number of the company
        department_request (DepartmentCreate): Pydantic model containing department details
        user_and_type (tuple): Tuple containing user details and type, obtained from dependency
    Returns:
        dict: A message confirming successful department creation
    Raises:
        HTTPException: In the following cases:
            - User is not an admin (403)
            - Company doesn't exist (404)
            - User is not part of the company (403)
            - Department name already exists (400)
            - Invalid HOD employee ID (400)
            - HOD not in staff list (400)
            - Invalid staff member employee ID (400)
            - Unexpected errors (400)
    """
    user, user_type = user_and_type
    if user_type != "admin":
        raise get_user_exception()
    
    company_id = user.get("company_id")
    
    try:
        # Verify the company exists
        company = await companies_collection.find_one({"registration_number": company_id})
        if not company:
            raise get_unknown_entity_exception()
        
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
        # Update department field for added employees
        for staff_id in staff_ids:
            await employees_collection.update_one(
            {"employee_id": staff_id, "company_id": company_id},
            {"$set": {"department": str(department_instance.id)}}
            )
        # Log the admin activity
        await log_admin_activity(
            admin_id=str(user.get("_id")), 
            type="department",
            status="success",
            action=f"Created department '{department_instance.name}'"
        )

        return {"message": "Department created successfully"}
    
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"An error occurred: {str(e)}"
        )


@router.get("/{department_id}/department-details")
async def get_department_details(
    department_id: str = Path(..., description="ID of the department to fetch details for."),
    q: Optional[str] = Query(None, description="Search across employee name, job title, employee ID, status, and work mode"),
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
    
    company_id = user.get("company_id")

    if not company_id:
        raise HTTPException(status_code=403, detail="Company ID not found in user data.")
    
    try:
        # Check if the department exists
        department = await departments_collection.find_one({"_id": ObjectId(department_id)})
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

        # Convert ObjectId to string
        department_id = str(department["_id"]) if "_id" in department else None

        # Build the department details
        department_details = {
            "department_id": department_id,
            "department_name": department.get("name", ""),
            "description": department.get("description", ""),
            "hod_details": hod_details,  # None if no valid HOD exists
        }

        # Build the query filter for employees
        employee_query = {"employee_id": {"$in": department.get("staffs", [])}}
        if q:
            search_regex = {"$regex": q, "$options": "i"}
            employee_query["$or"] = [
                {"first_name": search_regex},
                {"last_name": search_regex},
                {"job_title": search_regex},
                {"employee_id": search_regex},
                {"employment_status": search_regex},
                {"work_mode": search_regex}
            ]

        # Fetch department employees based on the query filter
        department_employees = await employees_collection.find(employee_query).to_list(None)
        department_details["staff_members"] = [
            {
                "employee_id": employee.get("employee_id", ""),
                "first_name": employee.get("first_name", ""),
                "last_name": employee.get("last_name", ""),
                "profile_image": employee.get("profile_image", ""),
                "job_title": employee.get("job_title", ""),
                "employment_status": employee.get("employment_status", ""),
                "work_mode": employee.get("work_mode", ""),
                "position": employee.get("position", ""),
            }
            for employee in department_employees
        ]

        return {"message": "Department details fetched successfully.", "data": department_details}
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"An error occurred: {str(e)}")


@router.put("/{department_id}/edit-department")
async def edit_department(
    department_request: DepartmentEdit,
    department_id: str = Path(..., description="ID of the department you want to edit"),
    user_and_type: tuple = Depends(get_current_user)
):
    user, user_type = user_and_type
    if user_type != "admin":
        raise get_user_exception()
    
    company_id = user.get("company_id")
    
    try:
        # Verify the company exists
        company = await companies_collection.find_one({"registration_number": company_id})
        if not company:
            raise get_unknown_entity_exception()

        # Fetch the department by its ID
        department = await departments_collection.find_one({"_id": ObjectId(department_id)})
        if not department:
            raise HTTPException(status_code=404, detail="Department not found")

        # Initialize the update data dictionary
        update_data = {}

        # Handle `name` update
        if department_request.name and department_request.name != department.get("name"):
            # Check if the department name (case insensitive) already exists
            existing_department = await departments_collection.find_one({
                "name": {"$regex": f"^{department_request.name}$", "$options": "i"},
                "company_id": company_id,
                "_id": {"$ne": department["_id"]}  # Exclude the current department
            })
            if existing_department:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Department name already exists")
            update_data["name"] = department_request.name

        # Handle `description` update
        if department_request.description:
            update_data["description"] = department_request.description

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
            # Update department field for added employees
            for staff_id in staff_ids_to_add:
                await employees_collection.update_one(
                    {"employee_id": staff_id, "company_id": company_id},
                    {"$set": {"department": str(department["_id"])}}
                )

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
async def delete_department(department_id: str, user_and_type: tuple = Depends(get_current_user)):
    """
    Deletes a department from the database.
    This async function removes a department entry from the departments collection. It performs
    authorization checks to ensure only admin users can delete departments within their company.
    Args:
        department_id (str): The unique identifier of the department to delete
        company_id (str): The registration number of the company
        user_and_type (tuple): A tuple containing user information and user type, obtained from get_current_user dependency
    Returns:
        dict: A message confirming successful deletion of the department
    Raises:
        HTTPException: If user is not authorized (not admin or wrong company)
        HTTPException: If company or department is not found
        HTTPException: If any other error occurs during the deletion process
    """

    user, user_type = user_and_type
    if user_type != "admin":
        raise get_user_exception()
    
    company_id = user.get("company_id")
    
    try:
        company = await companies_collection.find_one({"registration_number": company_id})
        if not company:
            raise get_unknown_entity_exception()
        
        department = await departments_collection.find_one({"_id": ObjectId(department_id)})
        if not department:
            raise get_unknown_entity_exception()
        
        await departments_collection.delete_one({"_id": department["_id"]})
        
        return {"message": "Department deleted successfully"}
    
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"An error occured - {e}")