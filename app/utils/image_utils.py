import os
import secrets

from fastapi import HTTPException, UploadFile

# BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# EMPLOYEE_UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads", "employee")
# ADMIN_UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads", "admin")

# Get the absolute path of the 'app' directory
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))  
BASE_UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")

EMPLOYEE_UPLOAD_DIR = os.path.join(BASE_UPLOAD_DIR, "employee")
ADMIN_UPLOAD_DIR = os.path.join(BASE_UPLOAD_DIR, "admin")

# Ensure directories exist
os.makedirs(EMPLOYEE_UPLOAD_DIR, exist_ok=True)
os.makedirs(ADMIN_UPLOAD_DIR, exist_ok=True)


def create_upload_directory(type: str):
    if type == "employee":
        os.makedirs(EMPLOYEE_UPLOAD_DIR, exist_ok=True)
    elif type == "admin":
        os.makedirs(ADMIN_UPLOAD_DIR, exist_ok=True)


def validate_file_extension(type: str, filename: str):
    extension_list = ["png", "jpg", "jpeg", "webp"]
    extension = os.path.splitext(filename)[-1].lower().replace(".", "")
    if extension not in extension_list:
        raise HTTPException(status_code=400, detail="Invalid file format")
    return extension


async def save_file(file: UploadFile, type: str, filename: str):
    file_content = await file.read()

    if type == "employee":
        file_path = os.path.join(EMPLOYEE_UPLOAD_DIR, filename)
    elif type == "admin":
        file_path = os.path.join(ADMIN_UPLOAD_DIR, filename)
    else:
        raise HTTPException(status_code=400, detail="Invalid file type")
    
    with open(file_path, "wb") as document:
        document.write(file_content)


async def create_media_file(type: str, file: UploadFile):
    filename = file.filename
    validate_file_extension(type=type, filename=filename)
    create_upload_directory(type=type)
    extension = os.path.splitext(filename)[-1].lower().replace(".", "")
    token_name = secrets.token_hex(10) + "." + extension
    await save_file(file=file, type=type, filename=token_name)

    return token_name