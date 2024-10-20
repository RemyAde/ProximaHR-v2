import random
import string
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, status, Query
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from db import companies_collection, admins_collection
from schemas.company import Company as CompanyCreate
from models.companies import Company
from utils import Token, send_verification_code, create_access_token, authenticate_user, get_current_user

router = APIRouter()


def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


@router.post("/register_company")
async def register_company(company: CompanyCreate, background_tasks: BackgroundTasks):
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
 
    user = await authenticate_user(company_id=company_id, pk=form_data.username, password=form_data.password, user_type=user_type)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid login details",
            headers={"WWW-Authenticate": "Bearer"},
        )

    expiry_time = timedelta(minutes=60)
    # token = create_access_token(payload={"sub": user['email'], "user_type": user_type, "company_id": user["company_id"]}, expiry=expiry_time)
    token = create_access_token(payload={"sub": form_data.username, "user_type": user_type, "company_id": user["company_id"]}, expiry=expiry_time)
    
    return {"access_token": token, "token_type": "bearer"}


@router.get("/")
async def get_company(company_id: str, user_and_type: tuple = Depends(get_current_user)):
    user, user_type = user_and_type

    company = await companies_collection.find_one({"registration_number": company_id})
    if not company:
        raise HTTPException(status_code=400, detail="Company not found")
    
    if user["company_id"] != company_id:
        raise HTTPException(status_code=401, detail="You are not authorized to access this page")
    
    return {"message": f"You are authorized to view {company_id}"}