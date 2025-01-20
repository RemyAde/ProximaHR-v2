from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from db import companies_collection, admins_collection
from schemas.admin import CreateAdmin
# from schemas.employee import ImageUpload
from models.admins import Admin
from app.utils.app_utils import get_current_user, hash_password
from image_utils import create_media_file

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


@router.post("/profile-image-upload")
async def upload_profile_image(request: Request, company_id: str, image_file: UploadFile = File(...), user_and_type: tuple = Depends(get_current_user)):
    user, user_type = user_and_type

    if company_id != user.get("company_id"):
        raise HTTPException(status_code=403, detail="You are not authorized to perform this function")

    if not image_file:
        raise HTTPException(status_code=400, detail="You must upload an image file")
    
    media_token_name = await create_media_file(type=user_type, file=image_file)

    result = await admins_collection.update_one(
        {"company_id": user["company_id"]}, 
        {"$set": 
         {"profile_image": f"{request.base_url}static/uploads/employee/{media_token_name}"}}
        )

    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Profile image not uploaded")

    return {"message": "Profile image uploaded successfully"}


@router.delete("/delete-profile-image")
async def delete_profile_image(company_id: str, user_and_type: tuple = Depends(get_current_user)):
    user, user_type = user_and_type

    if company_id != user["company_id"]:
        raise HTTPException(status_code=403, detail="You are not authorized to perform this action")
    
    result = await admins_collection.update_one(
        {"company_id": user["company_id"]},
        {"$set":
         {"profile_image": ""}}
         )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Image file not deleted.")