from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from routers import company, admin, employee
from config import settings


app = FastAPI(title=settings.PROJECT_TITLE)

app.include_router(company.router, prefix="/company", tags=["company"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.include_router(employee.router, prefix="/employee", tags=["employee"])

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins = [""],
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