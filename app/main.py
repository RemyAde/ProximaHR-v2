import logging 
from cron_jobs import scheduler

import uvicorn

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from routers import auth
from routers import (admin, employee, dashboard, employee_management, 
                     department, leave_management, payroll_management, 
                     attendance_management, attendance, report_analytics,
                     notifications)
from config import settings

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
directory = os.path.join(BASE_DIR, "static")

PROD_MODE = settings.PRODUCTION_MODE

app = FastAPI(title=settings.PROJECT_TITLE)

app.mount("/static", StaticFiles(directory=directory), name="static")

app.include_router(auth.router, prefix="/company", tags=["company"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.include_router(employee.router, prefix="/employee", tags=["employee"])
app.include_router(department.router, prefix="/departments", tags=["department"])
app.include_router(employee_management.router, prefix="/employee-management", tags=["employee_management"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
app.include_router(leave_management.router, prefix="/leave-management", tags=["leave_management"])
app.include_router(payroll_management.router, prefix="/payroll-management", tags=["payroll_management"])
app.include_router(attendance_management.router, prefix="/attendance-management", tags=["attendance_management"])
app.include_router(attendance.router, prefix="/attendance", tags=["attendance"])
app.include_router(report_analytics.router, prefix="/analytics", tags=["analytics"])
app.include_router(notifications.router, prefix="/notifications", tags=["notifications"])

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins = [
        "https://hrm-project-rosy.vercel.app",
        "http://localhost:3000",
        "http://localhost:3000",
        "http://127.0.0.1:5173"
        "http://127.0.0.1:5173"
        ],
    allow_credentials = True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,  # Set the logging level to INFO
    format='%(asctime)s - %(levelname)s - %(message)s',  # Log format
)

@app.get("/")
def index():
    return {"message": "Hello Proxima"}


if __name__ == "__main__":
    # Start cron job scheduler
    scheduler.start()

    if PROD_MODE == True:
    # Run Uvicorn without reload in production
        uvicorn.run("main:app", host="0.0.0.0", port=11000, reload=False)

    else:
        # Run Uvicorn with reload=True in development mode
        uvicorn.run("main:app", host="0.0.0.0", port=11000, reload=True)