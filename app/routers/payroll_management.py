from fastapi import APIRouter, Depends, HTTPException, status, Query
from datetime import datetime, timezone, timedelta
from pymongo import ASCENDING
from db import employees_collection, companies_collection
from utils.app_utils import get_current_user

router = APIRouter()


@router.get("/")
async def get_payroll(user_and_type: tuple = Depends(get_current_user)):
    """
    Retrieve payroll information for a specific company.
    This endpoint is restricted to admin users and can only be accessed by users
    belonging to the specified company.
    Args:
        company_id (str): The unique identifier of the company.
        user_and_type (tuple): A tuple containing user information and user type,
            obtained from the get_current_user dependency.
            First element is the user dict, second element is the user type string.
    Raises:
        HTTPException: 
            - 403 if the user is not an admin
            - 403 if the user doesn't belong to the specified company
    Returns:
        dict: Payroll information for the specified company.
    """

    user, user_type = user_and_type

    if user_type != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not authorized to view this page")
    
    company_id = user["company_id"]
    if not company_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Company ID not found")

@router.get("/summary")
async def get_payroll_summary(
    user_and_type: tuple = Depends(get_current_user)
):
    """
    Retrieve a summary of payroll information for a specific company.
    This endpoint is restricted to admin users and can only be accessed by users
    belonging to the specified company.
    Args:
        user_and_type (tuple): A tuple containing user information and user type,
            obtained from the get_current_user dependency.
            First element is the user dict, second element is the user type string.
    Raises:
        HTTPException: 
            - 403 if the user is not an admin
            - 403 if the user doesn't belong to the specified company
            - 500 if an exception occurs during the database operation
    Returns:
        dict: Summary of payroll information for the specified company
    """
    user, user_type = user_and_type

    if user_type != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="You are not authorized to view this page"
            )

    company_id = user["company_id"]
    if not company_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Company ID not found")
    company_id = user["company_id"]
    if not company_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Company ID not found")

    try:
        # 1. Payroll Cost: Sum of base_salary + allowances + company_match
        payroll_cost_cursor = employees_collection.aggregate([
            {
                "$match": {
                    "company_id": company_id,
                    "employment_status": {"$ne": "inactive"}  # Exclude inactive employees
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total_payroll_cost": {
                        "$sum": {
                            "$add": [
                                "$base_salary",
                                {"$ifNull": ["$overtime_hours_allowance", 0]},
                                {"$ifNull": ["$housing_allowance", 0]},
                                {"$ifNull": ["$transport_allowance", 0]},
                                {"$ifNull": ["$medical_allowance", 0]},
                                {"$ifNull": ["$company_match", 0]}
                            ]
                        }
                    }
                }
            }
        ])

        payroll_cost_result = await payroll_cost_cursor.to_list(length=1)
        payroll_cost = payroll_cost_result[0]["total_payroll_cost"] if payroll_cost_result else 0

        # 2. Pending Payment: Count of payment_status set to 'unpaid'
        pending_payment_count = await employees_collection.count_documents({
            "company_id": company_id,
            "payment_status": "unpaid"
        })

        # 3. Approved Payrolls: Count of payment_status set to 'paid'
        approved_payroll_count = await employees_collection.count_documents({
            "company_id": company_id,
            "payment_status": "paid"
        })

        # 4. Upcoming Salary: Last date of the current month
        now = datetime.now(timezone.utc)
        first_day_next_month = (
            datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
            if now.month < 12
            else datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
        )
        last_date_of_month = first_day_next_month - timedelta(days=1)

        # Return results
        return {
            "payroll_cost": payroll_cost,
            "pending_payment_count": pending_payment_count,
            "approved_payroll_count": approved_payroll_count,
            "upcoming_salary_date": last_date_of_month.date().isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cost-trend")
async def get_payroll_cost_trend(
    year: int = Query(None, description="Year to view payroll trend"),
    user_and_type: tuple = Depends(get_current_user)
):
    """
    Retrieves the payroll cost trend data for a specific company over a year.
    This async function calculates and returns monthly payroll costs for a company,
    aggregating various salary components for all active employees.
    Args:
        year (int, optional): The year to analyze payroll trends for. Defaults to current year
        user_and_type (tuple): Tuple containing user information and type, obtained from dependency
    Returns:
        dict: A dictionary containing:
            - year (int): The analyzed year
            - payroll_cost_trend (list): List of dictionaries containing:
                - month (int): Month number (1-12)
                - payroll_cost (float): Total payroll cost for that month
    Raises:
        HTTPException: 
            - 403: If user is not admin or not authorized for the company
            - 404: If no employee data exists for the company
            - 400: If specified year is invalid
            - 500: For any other server-side errors
    Notes:
        - Only admin users can access this endpoint
        - Includes base salary and all allowances in cost calculation
        - Inactive employees are excluded from calculations
        - Returns 0 for months with no payroll data
    """

    user, user_type = user_and_type

    if user_type != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="You are not authorized to view this page"
        )

    company_id = user["company_id"]
    if not company_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Company ID not found")
    
    try:
        # Get the minimum year from the earliest `date_created` field
        earliest_employee = await employees_collection.find_one(
            {"company_id": company_id},
            sort=[("date_created", ASCENDING)],
            projection={"date_created": 1}
        )
        if not earliest_employee or "date_created" not in earliest_employee:
            raise HTTPException(status_code=404, detail="No employee data found for the specified company")

        min_year = earliest_employee["date_created"].year
        current_year = datetime.now(timezone.utc).year

        # Validate the year parameter
        if year is None:
            year = current_year  # Default to the current year if no year is provided
        elif year < min_year or year > current_year:
            raise HTTPException(
                status_code=400,
                detail=f"Year must be between {min_year} and {current_year}"
            )

        # Aggregate payroll cost per month for the specified year and company
        pipeline = [
            {"$match": 
             {"company_id": company_id, 
              "employment_status": {"$ne": "inactive"}, 
              "date_created": {"$gte": datetime(year, 1, 1), 
                               "$lt": datetime(year + 1, 1, 1)}}},
            {"$group": {
                "_id": {"month": {"$month": "$date_created"}},
                "monthly_payroll_cost": {
                    "$sum": {
                        "$add": [
                            "$base_salary",
                            {"$ifNull": ["$overtime_hours_allowance", 0]},
                            {"$ifNull": ["$housing_allowance", 0]},
                            {"$ifNull": ["$transport_allowance", 0]},
                            {"$ifNull": ["$medical_allowance", 0]},
                            {"$ifNull": ["$company_match", 0]}
                        ]
                    }
                }
            }},
            {"$sort": {"_id.month": 1}}  # Sort by month
        ]

        payroll_cost_cursor = employees_collection.aggregate(pipeline)
        payroll_cost_data = await payroll_cost_cursor.to_list(length=12)

        # Create a response with payroll costs for all 12 months (fill missing months with 0)
        monthly_payroll_cost = {month: 0 for month in range(1, 13)}
        for entry in payroll_cost_data:
            month = entry["_id"]["month"]
            monthly_payroll_cost[month] = entry["monthly_payroll_cost"]

        return {
            "company_id": company_id,
            "year": year,
            "payroll_cost_trend": [
                {"month": month, "payroll_cost": monthly_payroll_cost[month]}
                for month in range(1, 13)
            ]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@router.get("/cost-distribution")
async def payroll_cost_distribution(
    user_and_type: tuple = Depends(get_current_user)
):
    """
    Endpoint to calculate payroll cost distribution.
    Filters employees based on company_id and excludes those with employment_status as 'inactive'.
    """

    user, user_type = user_and_type

    if user_type != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="You are not authorized to view this page"
        )

    company_id = user["company_id"]
    if not company_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Company ID not found")
    
    try:
        # Query active employees for the company
        active_employees_cursor = employees_collection.find(
            {"company_id": company_id, "employment_status": {"$ne": "inactive"}}
        )
        active_employees = await active_employees_cursor.to_list(None)

        # Initialize totals
        total_net_pay = 0
        total_deductions = 0
        total_allowances_and_contributions = 0

        # Calculate for each employee
        for employee in active_employees:
            base_salary = employee.get("base_salary", 0)
            paye_deduction = employee.get("paye_deduction", 0)
            employee_contribution = employee.get("employee_contribution", 0)
            overtime_allowance = employee.get("overtime_hours_allowance", 0)
            housing_allowance = employee.get("housing_allowance", 0)
            transport_allowance = employee.get("transport_allowance", 0)
            medical_allowance = employee.get("medical_allowance", 0)
            company_match = employee.get("company_match", 0)

            # Calculate individual components
            net_pay = base_salary - (paye_deduction + employee_contribution)
            deductions = paye_deduction + employee_contribution
            allowances_and_contributions = (
                overtime_allowance
                + housing_allowance
                + transport_allowance
                + medical_allowance
                + company_match
            )

            # Update totals
            total_net_pay += net_pay
            total_deductions += deductions
            total_allowances_and_contributions += allowances_and_contributions

        # Return the distribution
        return {
            "net_pay": total_net_pay,
            "deductions": total_deductions,
            "allowances_and_contributions": total_allowances_and_contributions,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@router.get("/employees")
async def get_employees(
    page: int = 1,
    page_size: int = 10,
    name: str = Query(None, description="Search by employee's first name, last name, or employee ID."),
    year: int = Query(None, description="Year to view payroll data"),
    department: str = Query(None, description="Department to view payroll data"),
    status: str = Query(None, description="Employee payment status: paid|unpaid"),
    allowance: bool = Query(False, description="Option to view allowances and contributions"),
    user_and_type: tuple = Depends(get_current_user)
):
    """
    Retrieve employee payroll information for a specific company.
    This endpoint is restricted to admin users and can only be accessed by users
    belonging to the specified company.
    Args:
        page (int): The page number to retrieve (default: 1)
        page_size (int): The number of records to retrieve per page (default: 10)
        name (str): Search by employee's first name, last name, or employee ID.
        year (int): Year to view payroll data.
        department (str): Department to view payroll data.
        status (str): Employee payment status: paid|unpaid.
        allowance (bool): Option to view allowances and contributions.
        user_and_type (tuple): A tuple containing user information and user type,
            obtained from the get_current_user dependency.
            First element is the user dict, second element is the user type string.
    Raises:
        HTTPException: 
            - 403 if the user is not an admin
            - 403 if the user doesn't belong to the specified company
            - 404 if no employee data exists for the company
            - 400 if specified year is invalid
            - 500 if an exception occurs during the database operation
    Returns:
        dict: Employee payroll information for the specified company.
    """
    
    user, user_type = user_and_type

    company_id = user["company_id"]
    if not company_id:
        raise HTTPException(status_code=400, detail="Company ID not found")
    
    existing_company = await companies_collection.find_one(
        {"registration_number": company_id}
    )
    if not existing_company:
        raise HTTPException(status_code=404, detail="Company record not found")

    if user_type != "admin":
        raise HTTPException(
            status_code=403,
            detail="You are not authorized to view this page"
        )

    try:
        if page < 1:
            page = 1

        skip = (page - 1) * page_size

        query_filter = {
            "company_id": company_id,
            "employment_status": {"$ne": "inactive"}  # Exclude inactive employees
        }

        if department:
            query_filter["department"] = {"$regex": f"^{department}$", "$options": "i"}

        if name:
            query_filter["$or"] = [
                {"first_name": {"$regex": name, "$options": "i"}},
                {"last_name": {"$regex": name, "$options": "i"}},
                {"employee_id": {"$regex": name, "$options": "i"}}
            ]

        if status:
            query_filter["payment_status"] = {"$regex": f"^{status}$", "$options": "i"}

        earliest_employee = await employees_collection.find_one(
            {"company_id": company_id},
            sort=[("date_created", ASCENDING)],
            projection={"date_created": 1}
        )
        
        if not earliest_employee or "date_created" not in earliest_employee:
            raise HTTPException(status_code=404, detail="No employee data found for the specified company")

        min_year = earliest_employee["date_created"].year
        current_year = datetime.now(timezone.utc).year

        # Validate the year parameter
        if year is None:
            year = current_year
        elif year < min_year or year > current_year:
            raise HTTPException(
                status_code=400,
                detail=f"Year must be between {min_year} and {current_year}"
            )

        query_filter["date_created"] = {
            "$gte": datetime(year, 1, 1),
            "$lt": datetime(year + 1, 1, 1)
        }

        employees_list = await employees_collection.find(query_filter).skip(skip).limit(page_size).to_list(length=page_size)

        # Prepare the response data
        employees_data = []
        
        for employee in employees_list:
            data = {
                "name": f"{employee['first_name']} {employee['last_name']}",
                "department": employee.get("department", ""),
                "base_salary": employee.get("base_salary", ""),
                "deductions": employee.get("paye_deduction", 0) + employee.get("employee_contribution", 0),
                "net_pay": employee.get("net_pay", ""),
                "payment_status": employee.get("payment_status", "")
            }

            # Include allowances if requested
            if allowance:
                data.update({
                    "transport_allowance": employee.get("transport_allowance", None),
                    "medical_allowance": employee.get("medical_allowance", None),
                    "overtime_hours_allowance": employee.get("overtime_hours_allowance", None),
                    "housing_allowance": employee.get("housing_allowance", None),
                    "company_match": employee.get("company_match", None)
                })

            employees_data.append(data)

        return {"employees_data": employees_data}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An exception occurred - {e}")
