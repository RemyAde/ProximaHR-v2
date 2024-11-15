from motor.motor_asyncio import AsyncIOMotorClient
from config import settings


client = AsyncIOMotorClient(settings.MONGODB_URL)
db = client.hr_system


companies_collection = db.companies
admins_collection = db.admins
employees_collection = db.employees
random_codes_collection = db.random_codes
departments_collection = db.departments