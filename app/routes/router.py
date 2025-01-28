"""Central router configuration for the ATS Network application."""
from fastapi import APIRouter

# Create main router that will hold all sub-routers
api_router = APIRouter()

# This will be used by other modules to get reference to the main router
def get_api_router():
    return api_router