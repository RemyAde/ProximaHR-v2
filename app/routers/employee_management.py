from datetime import datetime
from typing import Optional
from pymongo.errors import PyMongoError
from fastapi import APIRouter, Depends, Query, status, HTTPException
from schemas.employee import CreateEmployee, EditEmployee
from models.employees import Employee
from db import client, employees_collection, companies_collection, departments_collection
from utils.app_utils import get_current_user, generate_password, hash_password
from utils.activity_utils import log_admin_activity
from exceptions import get_unknown_entity_exception, get_user_exception


router = APIRouter()


@router.get("/all-employees")
async def list_employees(
    page: int = 1,
    page_size: int = 10,
    department_name: Optional[str] = None,  # Optional department name query parameter
    name: Optional[str] = Query(
        None,
        description="Search by employee's first name, last name, or employee ID."
    ),  # Optional name/employee_id query parameter with documentation
    user_and_type: tuple = Depends(get_current_user),
):
    """
    Retrieve a paginated list of employees for a specific company with optional filtering.
    This async function fetches employees from the database with various filter options
    and pagination support. It requires admin privileges to access.
    Args:
        company_id (str): The registration number of the company
        page (int, optional): The page number for pagination. Defaults to 1.
        page_size (int, optional): Number of items per page. Defaults to 10.
        department_name (Optional[str], optional): Filter employees by department name. Defaults to None.
        name (Optional[str], optional): Search term for employee's first name, last name, or employee ID.
            Case-insensitive search. Defaults to None.
        user_and_type (tuple): Tuple containing user information and user type from authentication dependency.
    Returns:
        dict: A dictionary containing:
            - staff_size: Total number of employees in the company
            - List of employee dictionaries with following fields:
                - company_id: Company registration number
                - profile_image: URL of employee's profile image
                - employee_id: Unique identifier for the employee
                - name: Combined first and last name
                - job_title: Employee's job title
                - department: Employee's department
                - work_mode: Employee's work mode (e.g., remote, office)
                - position: Employee's position
                - employment_status: Current employment status
    Raises:
        HTTPException: 
            - 401 if user is not admin
            - 404 if company not found
            - 401 if user's company_id doesn't match requested company_id
            - 400 for any other processing errors
    """
    
    user, user_type = user_and_type
    if user_type != "admin":
        raise get_user_exception()
    
    company_id = user.get("company_id")
    if not company_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized user!")

    try: 
        data = []

        company = await companies_collection.find_one({"registration_number": company_id})
        if not company:
            raise get_unknown_entity_exception()

        
        data.append({
            "staff_size": company.get("staff_size", "")
        })
        
        if page < 1:
            page = 1

        skip = (page - 1) * page_size

        # Build the query filter dynamically, excluding inactive employees
        query_filter = {
            "company_id": company_id,
            "employment_status": {"$ne": "inactive"}
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
                "email": employee.get("email", ""),
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
    user_and_type: tuple = Depends(get_current_user)
):
    """
    Fetch detailed information for a specific employee.
    This endpoint retrieves comprehensive details of an employee, accessible only by admin
    or HR users within the same company.
    Args:
        employee_id (str): The unique identifier of the employee.
        company_id (str): The registration number of the company.
        user_and_type (tuple): A tuple containing the current user and their type (from dependency).
    Returns:
        dict: A dictionary containing the employee data with sensitive fields excluded.
            Format: {"data": serialized_employee_dict}
    Raises:
        HTTPException (404): If the company or employee is not found.
        HTTPException (403): If the user is not authorized (not admin or HR).
        HTTPException (401): If the user is not from the same company.
    """
    user, user_type = user_and_type
    company_id = user.get("company_id")

    company = await companies_collection.find_one({"registration_number": company_id})
    if not company:
        raise get_unknown_entity_exception()

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
async def create_employee_profile(employee_request: CreateEmployee, user_and_type: tuple = Depends(get_current_user)):
    """
    Creates a new employee profile in the system with associated company updates.
    This asynchronous function handles the creation of an employee profile, including salary calculations,
    and company staff size updates within a transaction.
    Args:
        employee_request (CreateEmployee): Pydantic model containing employee details including:
            - employee_id
            - email
            - base_salary
            - paye_deduction (percentage)
            - employee_contribution (percentage)
            - company_match (percentage)
            - date_of_birth
            - department (optional)
        user_and_type (tuple): Tuple containing user details and user type from authentication dependency
    Returns:
        dict: A dictionary containing:
            - message: Success message
            - data: Dictionary with employee_id and generated password
    Raises:
        HTTPException: 
            - 400: If company not found or employee already exists
            - 401: If user is not authorized or not an admin
            - 500: If database transaction fails
    Notes:
        - Function performs all database operations within a transaction
        - Automatically calculates net pay based on salary and deductions
        - Updates company staff counts
        - Generates and hashes a password for the new employee
    """

    user, user_type = user_and_type

    if user_type != "admin":
        raise HTTPException(status_code=401, detail="Unauthorized user!")
    
    company_id = user.get("company_id")
    if not company_id:  
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized user!")

    company = await companies_collection.find_one({"registration_number": company_id})
    if not company:
        raise HTTPException(status_code=400, detail="Company not found")
    
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

    await log_admin_activity(admin_id=str(user["_id"]), type="create_employee", action=f"Created {employee_instance.first_name} profile", status="success")

    return {"message": "Employee account created successfully", "data": data}


@router.put("/{employee_id}/edit-employee")
async def edit_employee_profile(
    employee_id: str,
    employee_updates: EditEmployee,
    user_and_type: tuple = Depends(get_current_user)
):
    """
    Edit an employee's profile information.
    This function allows an admin user to modify an existing employee's profile details.
    The admin must belong to the same company as the employee to perform the edit.
    Args:
        employee_id (str): The unique identifier of the employee to be edited.
        employee_updates (EditEmployee): Pydantic model containing the fields to update.
        user_and_type (tuple): Tuple containing user information and user type from authentication.
    Returns:
        dict: A dictionary containing a success message and the updated fields.
    Raises:
        HTTPException: 
            - 401 if user is not an admin
            - 404 if employee is not found
            - 403 if admin is not from the same company as employee
            - 400 if no update data is provided or update fails
    Example:
        >>> response = await edit_employee_profile(
        ...     "EMP123",
        ...     EditEmployee(first_name="John", last_name="Doe"),
        ...     (current_user, "admin")
        ... )
    """
    
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
    
    await log_admin_activity(admin_id=str(user["_id"]), type="update_employee", action=f"Edited '{employee['first_name']}' profile", status="success")

    return {"message": "Employee profile updated successfully", "updated_fields": update_data}


@router.post("/{employee_id}/suspend-employee")
async def suspend_employee(
    employee_id: str,
    suspension_data: dict,
    user_and_type: tuple = Depends(get_current_user)
):
    """
    Suspend an employee for a specified period.
    This function updates an employee's status to 'suspended' and records suspension details.
    Only company administrators can suspend employees within their own company.
    Args:
        employee_id (str): The ID of the employee to suspend
        suspension_data (dict): Dictionary containing suspension details including:
            - start_date (str): Suspension start date in "YYYY-MM-DD" format
            - end_date (str): Suspension end date in "YYYY-MM-DD" format
        user_and_type (tuple): Tuple containing user information and type (from dependency)
    Raises:
        HTTPException: 
            - 403: If user is not an admin
            - 404: If employee is not found
            - 400: If end date is not after start date
        UserException: If company_id doesn't match user's company
    Returns:
        dict: Message confirming successful suspension
    """
    
    user, user_type = user_and_type
    
    # Check if the user is authorized
    if user_type != "admin":
        raise HTTPException(status_code=403, detail="Unauthorized user!")
    
    company_id = user.get("company_id")
    if not company_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized user!")
    company_id = user.get("company_id")
    if not company_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized user!")
    
    # Find the employee
    employee = await employees_collection.find_one({"employee_id": employee_id})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    if employee["company_id"] != company_id:
        raise get_user_exception()

    
    if employee["company_id"] != company_id:
        raise get_user_exception()

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

    await log_admin_activity(admin_id=str(user["_id"]), type="suspend_employee", action=f"Suspended {employee['first_name']} profile", status="success")
    
    return {"message": "Employee successfully suspended"}


@router.post("/{employee_id}/deactivate-employee")
async def deactivate_employee(
    employee_id: str,
    deactivation_data: dict,
    user_and_type: tuple = Depends(get_current_user)
):
    """
    Deactivates an employee by updating their employment status to 'inactive'.
    Reduces the company's staff size upon successful deactivation.
    Args:
        employee_id (str): The ID of the employee to deactivate.
        deactivation_data (dict): Data related to the deactivation (e.g., reason, date).
        user_and_type (tuple, optional): Tuple containing user info and type. Defaults to Depends(get_current_user).
    Raises:
        HTTPException: If user is not authorized (403) or employee is not found (404).
        UserException: If company_id doesn't match user's company_id.
    Returns:
        dict: A message confirming successful deactivation.
    Example:
        >>> deactivation_data = {"reason": "Retirement", "date": "2023-12-31"}
        >>> await deactivate_employee("comp123", "emp456", deactivation_data)
        {"message": "Employee successfully deactivated"}
    """
    
    user, user_type = user_and_type
    
    # Check if the user is authorized
    if user_type != "admin":
        raise HTTPException(status_code=403, detail="Unauthorized user!")
    
    company_id = user.get("company_id")
    if not company_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized user!")
    company_id = user.get("company_id")
    if not company_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized user!")
    
    # Find the employee
    employee = await employees_collection.find_one({"employee_id": employee_id})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    if employee["company_id"] != company_id:
        raise get_user_exception()
    
    if employee["company_id"] != company_id:
        raise get_user_exception()
    
    # Deactivate the employee
    result = await employees_collection.update_one(
        {"employee_id": employee_id},
        {
            "$set": {
                "employment_status": "inactive",
                "deactivation": deactivation_data
            }
        }
    )
    
    # Reduce company staff size if deactivation was successful
    if result.modified_count > 0:
        await companies_collection.update_one(
            {"registration_number": company_id},
            {"$inc": {"staff_size": -1}}
        )

    await log_admin_activity(
        admin_id=str(user["_id"]),
        type="deactivate_employee",
        action=f"Deactivated {employee['first_name']} profile",
        status="success"
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

        await log_admin_activity(admin_id=str(user["_id"]), type="create_employee", action=f"Created {employee_instance.first_name} profile", status="success")

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
