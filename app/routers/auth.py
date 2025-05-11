import random
import string
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, status, Query, Body
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import EmailStr
from datetime import timedelta
from db import companies_collection, admins_collection, employees_collection, random_codes_collection
from schemas.company import Company as CompanyCreate
from schemas.admin import EmailInput
from schemas.codes_and_pwds import Code, PasswordReset, ChangePassword
from models.companies import Company
from utils.app_utils import (Token, send_verification_code, create_access_token, 
                   authenticate_user, generate_email_verification_code,
                   store_random_codes_in_db, verify_verification_code, 
                   hash_password, verify_password, get_current_user)

router = APIRouter()


def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


@router.post("/register_company")
async def register_company(company: CompanyCreate):
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

    company_obj_dict = company.model_dump(exclude_unset=True)

    company_instance = Company(**company_obj_dict)

    await companies_collection.insert_one(company_instance.model_dump())

    await companies_collection.update_one(
        {"registration_number": company.registration_number},
        {"$set": {"company_url": f"login/{company.registration_number}"}}
    )

    data = [
        {"company_name": company.name,
         "registration_number": company.registration_number,
         "email": company.email
         }
    ]

    return {"message": "Company registered successfully", "data": data}


@router.post("/login", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(),
                                 user_type: str = Query(..., regex="^(admin|employee)$")
                                 ):
    """
    Handles user authentication and generates JWT access token.
    This endpoint validates user credentials and issues a JWT token for authenticated sessions.
    Args:
        form_data (OAuth2PasswordRequestForm): Form containing username (email) and password
        user_type (str): Type of user - must be either 'admin' or 'employee'
    Returns:
        dict: Contains the generated access token and token type
            {
                "access_token": str,
                "token_type": "bearer"
            }
    Raises:
        HTTPException: 401 Unauthorized if login credentials are invalid
    Example:
        >>> response = await login_for_access_token(form_data, "employee")
        >>> print(response)
        {"access_token": "eyJ0eXAiOiJKV1QiLC...", "token_type": "bearer"}
    """
    
    user = await authenticate_user(pk=form_data.username, password=form_data.password, user_type=user_type)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid login details",
            headers={"WWW-Authenticate": "Bearer"},
        )

    expiry_time = timedelta(days=1)
    
    token = create_access_token(payload={"sub": user["email"]}, expiry= expiry_time)
    
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


@router.post("/change-password")
async def change_password(passwords: ChangePassword = Body(...), user_and_type: tuple = Depends(get_current_user)):
    """
    Change the password for the authenticated user.
    This asynchronous function verifies the current password and updates it with a new one
    for both admin and employee users. It ensures the new password matches the confirmation
    and updates the appropriate collection in the database.
    Parameters:
    ----------
    passwords : ChangePassword
        A Pydantic model containing:
        - current_password: The user's current password
        - new_password: The desired new password
        - confirm_password: Confirmation of the new password
    user_and_type : tuple
        A tuple containing the user document and user type (admin/employee),
        obtained from the get_current_user dependency
    Returns:
    -------
    dict
        A dictionary with a success message indicating the password was changed
    Raises:
    ------
    HTTPException
        - 400: If the current password is invalid
        - 400: If the new password and confirm password do not match
    Notes:
    -----
    The function handles both admin and employee password changes by checking
    the user_type and updating the appropriate collection.
    """
   
    user, user_type = user_and_type

    if user_type == "admin":
        user = await admins_collection.find_one({"email": user["email"]})
        if not verify_password(plain_password=passwords.current_password, hashed_password=user["password"]):
            raise HTTPException(status_code=400, detail="Invalid current password")
        
    else:
        user = await employees_collection.find_one({"email": user["email"]})
        if not verify_password(plain_password=passwords.current_password, hashed_password=user["password"]):
            raise HTTPException(status_code=400, detail="Invalid current password")

    new_password = passwords.new_password
    confirm_password = passwords.confirm_password

    if new_password != confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    hashed_password = hash_password(new_password)
    
    if user_type == "admin":
        await admins_collection.update_one(
            {"email": user["email"]},
            {"$set": {"password": hashed_password}}
        )
    else:
        await employees_collection.update_one(
            {"email": user["email"]},
            {"$set": {"password": hashed_password}}
        )   

    return {"message": "Password changed successfully"}


@router.post("/logout")
async def logout(user: dict = Depends(get_current_user)):
    """
    Logout endpoint.
    In a stateless JWT scenario, logout is handled on the client side by discarding the token.
    This endpoint simply returns a success message.
    """
    return {"message": "Logged out successfully"}