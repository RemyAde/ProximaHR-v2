import random
import string
import secrets
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import BackgroundTasks, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from typing import Dict, Any, Tuple
import bcrypt
from jose import JWTError, jwt
from aiosmtplib import send
from email.mime.text import MIMEText
from db import admins_collection, employees_collection, companies_collection, random_codes_collection
from models.random_codes import RandomCodes
from config import settings

from datetime import datetime, timezone, timedelta, tzinfo

UTC = timezone.utc

oauth2_bearer = OAuth2PasswordBearer(tokenUrl="auth/login/")

secret_key = settings.SECRET_KEY
algorithm = settings.ALGORITHM

smtp_user = settings.SMTP_USER
smtp_pwd = settings.SMTP_USER_PWD
smtp_host = settings.SMTP_HOST
smtp_port = settings.SMTP_PORT

scheduler = BackgroundScheduler()


class Token(BaseModel):
    access_token: str
    token_type: str


def generate_password(length: int = 8) -> str:
    # Define the allowed characters: uppercase, lowercase, and digits
    allowed_characters = string.ascii_letters + string.digits
    
    # Use secrets.choice to securely choose random characters
    password = ''.join(secrets.choice(allowed_characters) for _ in range(length))
    
    return password


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed_password


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if isinstance(hashed_password, str):
        hashed_password = hashed_password.encode('utf-8')

    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password)


def create_access_token(payload: Dict[str, Any], expiry: timedelta):
    data_to_encode = {"data": payload}
    expiry_delta = datetime.now(UTC) + expiry
    data_to_encode.update({"exp": expiry_delta})
    encoded_data: str =  jwt.encode(data_to_encode, secret_key, algorithm)

    return encoded_data


async def authenticate_user(pk: str, password: str):
    """
    authenticates user
    args:-
        - pk: primary key (email for admin and for employees)
        - password: password
    """
    is_valid_email = "@" in pk and "." in pk
    if not is_valid_email:
        return False
    
    user = await admins_collection.find_one({"email": pk})
    if not user:
        user = await employees_collection.find_one({"email": pk})
        if not user:
            return False
    
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

        if pk is None:
            print("Invalid user")
            raise HTTPException(status_code=401, detail="Could not validate user.")
        
        user = await admins_collection.find_one({"email": pk})
        user_type = "admin"
        
        if not user:
            user = await employees_collection.find_one({"email": pk})
            user_type = "employee"
        
            if not user:
                raise HTTPException(status_code=401, detail="User not found.")
        
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


def generate_email_verification_code(grace_period = timedelta(minutes=60)) -> Tuple[int, datetime]:
    random_code = random.randint(100000, 999999)
    expiration_time = datetime.now(UTC) + grace_period
    return random_code, expiration_time


async def store_random_codes_in_db(user, code: int, expiration_time: datetime):

    try:
        existing_user = await random_codes_collection.find_one({"user_email": user["email"]})
        if existing_user:
            rate_limit = existing_user.get("updated_at")
            if rate_limit is not None and rate_limit.tzinfo is None:
                rate_limit  = rate_limit.replace(tzinfo=UTC)

                if rate_limit and (datetime.now(UTC) - rate_limit).total_seconds() < 60:
                    raise HTTPException(status_code=429, detail="You can only request a new verification email every 1 minute.")
                
            exp_time = datetime.now(UTC) + timedelta(minutes=60)
            random_codes_collection.update_one({"user_email": user["email"]}, {"$set": {"code": code, "expiration_time": exp_time, "verified": False}})

        else:
            code_instance = RandomCodes(
            user_email=user["email"],
            code = code,
            expiration_time=expiration_time,
            updated_at = datetime.now(UTC)
        )
            await random_codes_collection.insert_one(code_instance.model_dump())

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"An error occured - {e}")


async def verify_verification_code(email: str, verification_code: int):
    try:
        code_to_verify = await random_codes_collection.find_one({"user_email": email})
        if not code_to_verify:
            raise HTTPException(status_code=400, detail="Email address not found")
        
        if str(verification_code) != str(code_to_verify.get("code")):
            raise HTTPException(status_code=400, detail="Invalid verification code.")
        
        expiration_time = code_to_verify.get("expiration_time")
        if expiration_time is not None and expiration_time.tzinfo is None:
            expiration_time = expiration_time.replace(tzinfo=UTC)

        if expiration_time is None or datetime.now(UTC) > expiration_time:
            raise HTTPException(status_code=400, detail="Verification code has expired")
        
        await random_codes_collection.update_one(
            {"user_email": email},
            {"$set": {"verified": True}}
        )
        
        return {"message": "Verification code verified successfully"}
    
    except Exception as e:
        if code_to_verify:
            print("user_code", verification_code)
            print("retrieved-code", code_to_verify.get("code"))
        raise HTTPException(status_code=400, detail=f"An error occurred - {e}")