from fastapi import BackgroundTasks, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from typing import Dict, Any
import bcrypt
from jose import JWTError, jwt
from aiosmtplib import send
from email.mime.text import MIMEText
from db import admins_collection, employees_collection, companies_collection
from config import settings

from datetime import datetime, timezone, timedelta

UTC = timezone.utc

oauth2_bearer = OAuth2PasswordBearer(tokenUrl="company/login/")

secret_key = settings.SECRET_KEY
algorithm = settings.ALGORITHM

smtp_user = settings.SMTP_USER
smtp_pwd = settings.SMTP_USER_PWD
smtp_host = settings.SMTP_HOST
smtp_port = settings.SMTP_PORT


class Token(BaseModel):
    access_token: str
    token_type: str


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed_password


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def create_access_token(payload: Dict[str, Any], expiry: timedelta):
    data_to_encode = {"data": payload}
    expiry_delta = datetime.now(UTC) + expiry
    data_to_encode.update({"exp": expiry_delta})
    encoded_data: str =  jwt.encode(data_to_encode, secret_key, algorithm)

    return encoded_data


async def authenticate_user(company_id: str, pk: str, password: str, user_type: str):
    """
    authenticates user
    args:-
        - pk: primary key (email for admin or employee_id for employees)
        - user_type: admin or employee
    """
    company = await companies_collection.find_one({"registration_number": company_id})
    if not company:
        raise HTTPException(status_code=400, detail="Company not found")

    if user_type == "admin":
        user =  await admins_collection.find_one({"company_id": company_id, "email": pk})
        if not user:
            return False
    if user_type == "employee":
        user = await employees_collection.find_one({"company_id": company_id, "employee_id": pk})
        if not user:
            return False
    # else:
    #     raise HTTPException(status_code=400, detail="Invalid user input")
    
    hashed_password = user["password"]
    if not verify_password(plain_password=password, hashed_password=hashed_password):
        return False
    return user


async def get_current_user(token: str = Depends(oauth2_bearer)) -> tuple:
    try:
        # Decode the JWT
        payload = jwt.decode(token, secret_key, algorithms=algorithm)
        data = payload.get("data")  # Access the "data" object
        
        if data is None:
            raise HTTPException(status_code=401, detail="Invalid token data.")
        
        pk: str = data.get("sub")
        user_type: str = data.get("user_type")
        company_id: str = data.get("company_id")

        if pk is None or user_type is None:
            print("Invalid user")
            raise HTTPException(status_code=401, detail="Could not validate user.")
        
        if user_type == "admin":
            user = await admins_collection.find_one({"company_id": company_id, "email": pk})
            if not user:
                raise HTTPException(status_code=401, detail="Admin not found.")
            
        elif user_type == "employee":
            user = await employees_collection.find_one({"company_id": company_id, "employee_id": pk})
            if not user:
                raise HTTPException(status_code=401, detail="Employee not found.")
        
        return user, user_type
    
    except JWTError as e:
        print(f"JWT Error {e}")
        raise HTTPException(status_code=401, detail="JWT Error - could not validate user.")


async def send_verification_code(email: str, subject: str, message:str, background_tasks: BackgroundTasks):
    message = MIMEText(message)
    message["From"] = smtp_user
    message["To"] = email
    message["Subject"] = subject

    background_tasks.add_task(send_email_async, message)


async def send_email_async(message):
    await send(message, hostname=smtp_host, port=smtp_port, username=smtp_user, password=smtp_pwd, use_tls=True)