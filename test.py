from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Test API",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Test endpoints
@app.get("/")
async def root():
    return {
        "status": "success",
        "message": "Root endpoint working"
    }

@app.get("/hello")
async def hello():
    return {
        "status": "success",
        "message": "Hello endpoint working"
    }