from fastapi import APIRouter, HTTPException
from db import companies_collection, employees_collection
from schemas.employee import CreateEmployee
from models.employees import Employee
from utils import hash_password

router = APIRouter()