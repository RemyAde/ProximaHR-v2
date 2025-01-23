import random
import string
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, status, Query, Body
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import EmailStr
from datetime import timedelta
from db import companies_collection, admins_collection, employees_collection, random_codes_collection
from schemas.company import Company as CompanyCreate
from schemas.admin import EmailInput
from schemas.codes_and_pwds import Code, PasswordReset
from models.companies import Company
from utils.app_utils import (Token, send_verification_code, create_access_token, 
                   authenticate_user, get_current_user, generate_email_verification_code,
                   store_random_codes_in_db, verify_verification_code, hash_password)

router = APIRouter()


def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


@router.post("/register_company")
async def register_company(company: CompanyCreate, background_tasks: BackgroundTasks):
    """
    Register a new company in the system.
    This function handles the registration of a new company by:
    1. Checking for existing companies with the same registration number or email
    2. Generating an admin creation code
    3. Creating and storing the company record
    4. Sending a verification email with the admin creation code
    Args:
        company (CompanyCreate): A Pydantic model containing company registration details
            including name, registration number, and email
        background_tasks (BackgroundTasks): FastAPI background tasks handler for async email sending
    Returns:
        dict: A dictionary containing:
            - message (str): Success message
            - data (list): List containing registered company details (name, registration number, email)
    Raises:
        HTTPException: 400 status code if company is already registered with given email or registration number
    Example:
        company_data = CompanyCreate(
            name="Example Corp",
            registration_number="12345",
            email="admin@example.com"
        result = await register_company(company_data, background_tasks)
    """

    existing_company = await companies_collection.find_one({
    "$or": [
        {"registration_number": company.registration_number},
        {"email": company.email}
        ]
        })
    if existing_company:
        raise HTTPException(status_code=400, detail="Company already registered")
    
    admin_code = generate_code()

    company_obj_dict = company.model_dump(exclude_unset=True)
    company_obj_dict["admin_creation_code"] = admin_code

    company_instance = Company(**company_obj_dict)

    await companies_collection.insert_one(company_instance.model_dump())

    await companies_collection.update_one(
        {"registration_number": company.registration_number},
        {"$set": {"company_url": f"login/{company.registration_number}"}}
    )

    email_subject = "Admin Creation Code"
    email_message = f"Your admin creation code is: {admin_code}. Use this to create your first admin account"

    await send_verification_code(email=company.email, subject=email_subject, message=email_message, background_tasks=background_tasks)

    data = [
        {"company_name": company.name,
         "registration_number": company.registration_number,
         "email": company.email
         }
    ]

    return {"message": "Company registered successfully", "data": data}


@router.post("/login", response_model=Token)
async def login_for_access_token(user_type: str, company_id: str = Query(...), form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Get an access token for a user.
    This function handles the login of a user by:
    1. Authenticating the user with the provided username and password
    2. Creating an access token for the user
    Args:
        user_type (str): The type of user (admin or employee)
        company_id (str): The
        form_data (OAuth2PasswordRequestForm): Pydantic model containing username and password
    Returns:
        dict: A dictionary containing:
            - access_token (str): JWT access token
            - token_type (str): Token type
    Raises:
        HTTPException: 401 status code if invalid login details
    Example:
        result = await login_for_access_token("admin", "12345", form_data)
    """
    user = await authenticate_user(company_id=company_id, pk=form_data.username, password=form_data.password, user_type=user_type)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid login details",
            headers={"WWW-Authenticate": "Bearer"},
        )

    expiry_time = timedelta(days=1)
    
    token = create_access_token(payload={"sub": form_data.username, "user_type": user_type, "company_id": user["company_id"]}, expiry=expiry_time)
    
    return {"access_token": token, "token_type": "bearer"}


@router.post("/send-verification-code-email")
async def send_reset_password_verification_email(email_data: EmailInput, background_tasks: BackgroundTasks):
    """
    Send a password reset verification code via email.
    This function handles the password reset process by:
    1. Verifying the email exists in the database
    2. Generating a verification code
    3. Storing the code in the database
    4. Sending the code to the user's email
    Args:
        email_data (EmailInput): Object containing the user's email address
        background_tasks (BackgroundTasks): FastAPI background tasks object for async email sending
    Returns:
        dict: A message indicating the reset code was sent successfully
    Raises:
        HTTPException: If the email address is not found in the database (status code 400)
    """

    email = email_data.email

    user = await admins_collection.find_one({"email": email})
    if not user:
        user = await employees_collection.find_one({"email": email})

    if not user:
        raise HTTPException(status_code=400, detail="Email address not found")

    code, expiration_time = generate_email_verification_code()

    await store_random_codes_in_db(user=user, code=code, expiration_time=expiration_time)

    email_subject = "New Password Code"
    email_message = f"Use this code to create your new password {code}.\n This code will expire after 1 hour."

    await send_verification_code(email=email, subject=email_subject, message=email_message, background_tasks=background_tasks)

    return {"Password reset code emaill sent successfully"}


@router.post("/verify-password-reset-verification-code")
async def verify_pwd_reset_code(email: EmailStr = Query(...), code: Code = Body(...)):
    """
    Verify password reset code for given email address.
    This endpoint verifies that the provided password reset code matches the one sent to the user's email.
    Args:
        email (EmailStr): Email address of the user requesting password reset.
        code (Code): Password reset code model containing the verification code sent to user's email.
    Raises:
        HTTPException: If code is invalid or expired, with status code 400.
        HTTPException: If email does not exist in the system, with status code 400.
    Returns:
        None: Returns nothing if verification is successful.
    """

    await verify_verification_code(email, code.code)


@router.post("/reset-password")
async def reset_password(email: EmailStr = Query(...), passwords: PasswordReset = Body(...)):
    """
    Resets the user's password after verification of reset code.
    This endpoint updates the password for either an admin or employee user after verifying that
    they have validated their password reset code via email.
    Args:
        email (EmailStr): The email address of the user requesting password reset
        passwords (PasswordReset): Object containing the new password to be set
    Returns:
        dict: A message confirming successful password reset
    Raises:
        HTTPException(400): If user code not found or not verified
        HTTPException(404): If user email not found in admin or employee database
    Example:
        ```
        POST /reset-password?email=user@example.com
        {
            "new_password": "newpassword123"
        }
        ```
    """

    new_password = passwords.new_password

    user_code = await random_codes_collection.find_one({"user_email": email})

    if not user_code:
        raise HTTPException(status_code=400, detail="User with email not found")
    
    if not user_code.get("verified"):
        raise HTTPException(status_code=400, detail="Password reset not verified. Please verify the code sent to your email")
    
    hashed_password = hash_password(new_password)

    admin = await admins_collection.update_one(
        {"email": email},
        {"$set": {"password": hashed_password}}
    )

    if admin.matched_count == 0:
        # If the email was not found in admins_collection, try employees_collection
        employee = await employees_collection.update_one(
            {"email": email},
            {"$set": {"password": hashed_password}}
        )
        
        if employee.matched_count == 0:
            raise HTTPException(status_code=404, detail="User with email not found in admin or employee database")
    
    return {"message": "Password reset successfully"}