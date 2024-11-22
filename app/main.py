import requests
import time 
import threading
import logging 

import uvicorn

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from routers import auth
from routers import admin, employee, dashboard, employee_management, department
from config import settings

PROD_MODE = settings.PRODUCTION_MODE

app = FastAPI(title=settings.PROJECT_TITLE)

app.include_router(auth.router, prefix="/company", tags=["company"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.include_router(employee.router, prefix="/employee", tags=["employee"])
app.include_router(department.router, prefix="/departments", tags=["department"])
app.include_router(employee_management.router, prefix="/employee-management", tags=["employee_management"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins = [
        "https://hrm-project-rosy.vercel.app",
        "http://localhost:3000",
        "http://127.0.0.1:3000"
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


def ping_server(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        logging.info(f"pinged {url} successfully.")

    except requests.exceptions.RequestException as e:
        logging.error(f"Error pinging {url}: {e}")


def main_ping():
    url = "https://proximahr.onrender.com"
    ping_interval = 600

    while True:
        ping_server(url)
        time.sleep(ping_interval)




if __name__ == "__main__":

    # Start the pinging function in a separate thread
    if PROD_MODE == True:
        ping_thread = threading.Thread(target=main_ping, daemon=True)
        ping_thread.start()

    # Run Uvicorn without reload in production
        uvicorn.run("main:app", host="0.0.0.0", port=11000, reload=False)

    else:
        # Run Uvicorn with reload=True in development mode
        uvicorn.run("main:app", host="0.0.0.0", port=11000, reload=True)