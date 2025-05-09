from motor.motor_asyncio import AsyncIOMotorClient
from config import settings

if settings.PRODUCTION_MODE:
    client = AsyncIOMotorClient(settings.MONGODB_URL)

else:
    client = AsyncIOMotorClient(settings.DEV_URL)
    
db = client.ProximaHR


companies_collection = db.companies
admins_collection = db.admins
employees_collection = db.employees
random_codes_collection = db.random_codes
departments_collection = db.departments
leaves_collection = db.leaves
timer_logs_collection = db.timer_logs
payroll_collection = db.payroll
notifications_collection = db.notifications
system_activity_collection = db.system_activity