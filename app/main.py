from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from routers import auth
from routers import admin, employee, dashboard
from config import settings


app = FastAPI(title=settings.PROJECT_TITLE)

app.include_router(auth.router, prefix="/company", tags=["company"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.include_router(employee.router, prefix="/employee", tags=["employee"])
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

@app.get("/")
def index():
    return {"message": "Hello Proxima"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=11000, reload=True)