from fastapi import APIRouter, Depends, HTTPException
from db import companies_collection, admins_collection
from schemas.admin import CreateAdmin
from models.admins import Admin
from utils import hash_password

router = APIRouter()


@router.post("/create-admin")
async def create_admin(admin_obj: CreateAdmin, company_id: str):
    company = await companies_collection.find_one({"registration_number": company_id})
    if not company:
        raise HTTPException(status_code=400, detail="Company not found")
    
    existing_admin = await admins_collection.find_one({
    "$or": [
        {"company_id": company_id},
        {"email": admin_obj.email}
        ]
        })
    
    if existing_admin:
        raise HTTPException(status_code=400, detail="Admin already registered")
    
    
    if company["admin_creation_code"] != admin_obj.admin_code:
        raise HTTPException(status_code=401, detail="Invalid admin creation code")
    
    if len(company.get("admin", [])) >= 1:
        raise HTTPException(status_code=400, detail="Admin limit reached")

    admin_obj_dict = admin_obj.model_dump(exclude_unset=True)
    admin_obj_dict["company_id"] = company_id
    admin_obj_dict["password"] = hash_password(password=admin_obj_dict["password"])

    admin_instance = Admin(**admin_obj_dict)

    await admins_collection.insert_one(admin_instance.model_dump())

    await companies_collection.update_one(
        {"registration_number": company_id},
        {"$push": {"admins": admin_instance.email},
         "$inc": {"staff_size": 1}}
    )

    return {"message": "Admin created successfully"}