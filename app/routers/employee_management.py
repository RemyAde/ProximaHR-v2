from datetime import datetime
from typing import Optional
from pymongo.errors import PyMongoError
from fastapi import APIRouter, Depends, Query, status, HTTPException
from schemas.employee import CreateEmployee, EditEmployee
from models.employees import Employee
from db import client, employees_collection, companies_collection, departments_collection
from utils.app_utils import get_current_user, generate_password, hash_password
from exceptions import get_unknown_entity_exception, get_user_exception


router = APIRouter()


@router.get("/all-employees")
async def list_employees(
    company_id: str,
    page: int = 1,
    page_size: int = 10,
    department_name: Optional[str] = None,  # Optional department name query parameter
    name: Optional[str] = Query(
        None,
        description="Search by employee's first name, last name, or employee ID."
    ),  # Optional name/employee_id query parameter with documentation
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
            query_filter["department"] = {"$regex": f"^{department_name}$", "$options": "i"}
        
        if name:  # Add name/employee_id search filter
            query_filter["$or"] = [
                {"first_name": {"$regex": name, "$options": "i"}},  # Case-insensitive search for first_name
                {"last_name": {"$regex": name, "$options": "i"}},   # Case-insensitive search for last_name
                {"employee_id": {"$regex": name, "$options": "i"}}  # Match employee_id
            ]

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
                "work_mode": employee.get("work_mode", ""),
                "position": employee.get("position", ""),
                "employment_status": employee.get("employment_status", ""),
            })

        return {"data": data}
    
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"An exception has occurred - {e}")


@router.get("/{employee_id}/employee")
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

    base_salary = employee_request.base_salary or 0
    paye_deduction_value = (employee_request.paye_deduction / 100) * base_salary
    employee_contribution_value = (employee_request.employee_contribution / 100) * base_salary
    company_match_value = (employee_request.company_match / 100) * base_salary

    employee_request_dict["paye_deduction"] = paye_deduction_value
    employee_request_dict["employee_contribution"] = employee_contribution_value
    employee_request_dict["company_match"] = company_match_value
    
    employee_request_dict["net_pay"] = base_salary - (paye_deduction_value + employee_contribution_value)

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


@router.put("/{employee_id}/edit-employee")
async def edit_employee_profile(
    employee_id: str,
    employee_updates: EditEmployee,
    user_and_type: tuple = Depends(get_current_user)
):
    user, user_type = user_and_type

    # Check if user is authorized
    if user_type != "admin":
        raise HTTPException(status_code=401, detail="Unauthorized user!")

    # Find the employee document
    employee = await employees_collection.find_one({"employee_id": employee_id})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    # Ensure the admin belongs to the same company
    if employee["company_id"] != user["company_id"]:
        raise HTTPException(status_code=403, detail="You are not authorized to edit this employee's profile")

    # Prepare the update payload, excluding unset fields
    update_data = employee_updates.model_dump(exclude_unset=True)
    
    if update_data["date_of_birth"]:
        update_data["date_of_birth"] = datetime.combine(employee_updates.date_of_birth, datetime.min.time())

    if update_data["employment_date"]:
        update_data["employment_date"] = datetime.combine(employee_updates.employment_date, datetime.min.time())

    if not update_data:
        raise HTTPException(status_code=400, detail="No data provided to update")

    # Update the employee document
    result = await employees_collection.update_one(
        {"employee_id": employee_id},
        {"$set": update_data}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Failed to update employee profile")

    return {"message": "Employee profile updated successfully", "updated_fields": update_data}


@router.post("/{employee_id}/suspend-employee")
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


@router.post("/{employee_id}/deactivate-employee")
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


@router.post("/test-create-employee-profile")
async def create_employee_profile(employee_request: CreateEmployee, company_id: str, user_and_type: tuple = Depends(get_current_user)):
    """Creates a new employee profile in the system.
    This endpoint is for testing purposes only and should not be consumed by frontend applications.
    It is used exclusively by backend engineers for testing employee creation flows.
    Args:
        employee_request (CreateEmployee): The employee data model containing all required employee information
        company_id (str): The registration number/ID of the company
        user_and_type (tuple): Tuple containing authenticated user info and user type, from dependency
    Returns:
        dict: A dictionary containing:
            - message (str): Success message
            - data (dict): Contains:
                - employee_id (str): The created employee's ID
                - password (str): The generated password for the employee
    Raises:
        HTTPException (400): If company not found or employee already exists
        HTTPException (401): If user is not from specified company or not an admin
        HTTPException (500): If employee creation fails for any reason
    Notes:
        - This endpoint is restricted to admin users only
        - Creates employee record with calculated salary deductions
        - Updates department staff count if department specified
        - Updates company staff size
        - Generates random password for employee
        - For testing purposes only - not for production use
    """
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

    base_salary = employee_request.base_salary or 0
    paye_deduction_value = (employee_request.paye_deduction / 100) * base_salary
    employee_contribution_value = (employee_request.employee_contribution / 100) * base_salary
    company_match_value = (employee_request.company_match / 100) * base_salary

    employee_request_dict["paye_deduction"] = paye_deduction_value
    employee_request_dict["employee_contribution"] = employee_contribution_value
    employee_request_dict["company_match"] = company_match_value
    
    employee_request_dict["net_pay"] = base_salary - (paye_deduction_value + employee_contribution_value)

    employee_request_dict["date_of_birth"] = datetime.combine(employee_request.date_of_birth, datetime.min.time())

    try:
        # Insert the employee
        employee_instance = Employee(**employee_request_dict)
        await employees_collection.insert_one(employee_instance.model_dump())

        # Update department if specified
        if employee_instance.department:
            await departments_collection.update_one(
                {"name": employee_instance.department},
                {
                    "$push": {"staffs": employee_instance.employee_id},
                    "$inc": {"staff_size": 1}
                }
            )

        # Update company staff size
        await companies_collection.update_one(
            {"registration_number": company_id},
            {"$inc": {"staff_size": 1}}
        )

        # Return success response
        data = {"employee_id": employee_instance.employee_id, "password": employee_pwd}
        return {"message": "Employee account created successfully", "data": data}

    except Exception as e:
        # If any operation fails, you'll need to handle cleanup manually
        # In production with transactions, this would be handled automatically
        print(f"Error creating employee: {e}")
        # Try to delete the employee if they were created
        await employees_collection.delete_one({"employee_id": employee_request.employee_id})
        raise HTTPException(status_code=500, detail=f"Failed to create employee: {str(e)}")