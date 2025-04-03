from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from db import companies_collection, admins_collection, employees_collection, departments_collection, leaves_collection, system_activity_collection
from schemas.admin import CreateAdmin, ExtendedAdmin
# from schemas.employee import ImageUpload
from models.admins import Admin
from utils.app_utils import get_current_user, hash_password
from utils.image_utils import create_media_file
from datetime import datetime, date, timezone
from pymongo.errors import PyMongoError

router = APIRouter()


@router.post("/create-admin")
async def create_admin(admin_obj: CreateAdmin, company_id: str):
    """
    Creates a new admin user for a company.
    This function performs the following operations:
    1. Verifies if the company exists
    2. Checks if an admin already exists for the company or email
    3. Validates the admin creation code
    4. Checks if the company has reached its admin limit
    5. Creates and stores the new admin
    6. Updates the company's admin list
    Args:
        admin_obj (CreateAdmin): The admin object containing admin details including:
            - email
            - password
            - admin_code
            - other admin-related fields
        company_id (str): The registration number of the company
    Returns:
        dict: A message confirming successful admin creation
    Raises:
        HTTPException (400): If company not found, admin already registered, or admin limit reached
        HTTPException (401): If invalid admin creation code provided
    Example:
        >>> admin = CreateAdmin(email="admin@example.com", password="secure123", admin_code="ABC123")
        >>> await create_admin(admin, "COMP123")
        {"message": "Admin created successfully"}
    """
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
        {"$push": {"admins": admin_instance.email}}
    )

    return {"message": "Admin created successfully"}


@router.post("/profile-image-upload")
async def upload_profile_image(request: Request, company_id: str, image_file: UploadFile = File(...), user_and_type: tuple = Depends(get_current_user)):
    """
    Uploads a profile image for the company admin.
    Args:
        request (Request): The FastAPI request object containing base URL information
        company_id (str): The ID of the company
        image_file (UploadFile): The image file to be uploaded
        user_and_type (tuple): Tuple containing user information and user type from authentication
    Returns:
        dict: A message indicating successful upload
    Raises:
        HTTPException: 
            - 403 if user is not authorized for the company
            - 400 if no image file is provided
            - 400 if profile image upload fails
    Dependencies:
        - get_current_user: For user authentication
        - create_media_file: For handling file upload
    """
    user, user_type = user_and_type

    if company_id != user.get("company_id"):
        raise HTTPException(status_code=403, detail="You are not authorized to perform this function")

    if not image_file:
        raise HTTPException(status_code=400, detail="You must upload an image file")
    
    media_token_name = await create_media_file(type=user_type, file=image_file)

    result = await admins_collection.update_one(
        {"company_id": user["company_id"]}, 
        {"$set": 
         {"profile_image": f"{request.base_url}static/uploads/admin/{media_token_name}"}}
        )

    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Profile image not uploaded")

    return {"message": "Profile image uploaded successfully"}


@router.delete("/delete-profile-image")
async def delete_profile_image(company_id: str, user_and_type: tuple = Depends(get_current_user)):
    """
    Delete profile image for a company admin.
    This function removes the profile image reference from the admin's document in the database.
    The user must be authenticated and belong to the company they are trying to modify.
    Args:
        company_id (str): The ID of the company whose admin's profile image should be deleted
        user_and_type (tuple): A tuple containing user information and type, obtained from authentication dependency
    Returns:
        None
    Raises:
        HTTPException: 
            - 403 if user is not authorized (company_id mismatch)
            - 400 if image reference could not be deleted
    """
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
    

@router.get("/profile")
async def get_admin_profile(company_id: str, user_and_type: tuple = Depends(get_current_user)):
    """
    Get the profile of the company admin.
    This function retrieves the profile details of the company admin from the database.
    The user must be authenticated and belong to the company they are trying to access.
    
    Args:
        company_id (str): The ID of the company whose admin profile should be retrieved
        user_and_type (tuple): A tuple containing user information and type, obtained from authentication dependency
    
    Returns:
        dict: The profile details of the company admin without sensitive fields
    
    Raises:
        HTTPException: 
            - 403 if user is not authorized (company_id mismatch or incorrect user type)
            - 400 if profile details could not be retrieved
    """
    user, user_type = user_and_type

    if company_id != user.get("company_id"):
        raise HTTPException(status_code=403, detail="You are not authorized to perform this action")
    
    if user_type != "admin":
        raise HTTPException(status_code=403, detail="You are not authorized to perform this action")
    
    try:
        admin = await admins_collection.find_one({"company_id": company_id})
        if not admin:
            raise HTTPException(status_code=400, detail="Profile details not found")

        # Exclude sensitive fields from the response
        admin.pop("password", None)
        admin.pop("date_created", None)

        # Convert ObjectId to string for JSON serialization
        if "_id" in admin:
            admin["_id"] = str(admin["_id"])

        return admin

    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"An unexpected error occurred: {str(e)}")


@router.put("/update-admin")
async def update_admin(
    admin_update: ExtendedAdmin, company_id: str, user_and_type: tuple = Depends(get_current_user)
):
    """
    Updates the admin model with fields defined in the ExtendedAdmin schema.
    The user must be authenticated and authorized as an admin for the specified company.
    
    Args:
        admin_update (ExtendedAdmin): An object containing the fields to update.
        company_id (str): The company identifier.
        user_and_type (tuple): Tuple with the authenticated user and its type.
    
    Returns:
        dict: A message confirming the successful update.
    
    Raises:
        HTTPException: If the user is not authorized or if the update fails.
    """
    user, user_type = user_and_type
    if company_id != user.get("company_id") or user_type != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to update admin profile")
    update_data = admin_update.model_dump(exclude_unset=True)

    dob = update_data.get("date_of_birth")
    if dob and isinstance(dob, date):
        # Convert date to datetime using midnight as time
        update_data["date_of_birth"] = datetime.combine(dob, datetime.min.time())
 
    result = await admins_collection.update_one(
        {"company_id": company_id},
        {"$set": update_data}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Update failed")
    return {"message": "Admin profile updated successfully"}


@router.get("/recent-activities", summary="Get today's activity summary for logged in admin")
async def get_admin_activities(user_and_type: tuple = Depends(get_current_user)):
    """
    Retrieve the 5 most recent admin-related activities for the logged-in admin.
    """
    user, user_type = user_and_type
    if user_type != "admin":
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    # Retrieve the 5 most recent activity-based entries from system_activity_collection for the logged-in admin
    activities = await system_activity_collection.find({
        "admin_id": str(user["_id"])
    }).sort("timestamp", -1).limit(5).to_list(length=None)

    # Convert ObjectId fields to string
    for activity in activities:
        if '_id' in activity:
            activity['_id'] = str(activity['_id'])
        if 'admin_id' in activity:
            activity['admin_id'] = str(activity['admin_id'])
    
    return {"admin_activities": activities}
