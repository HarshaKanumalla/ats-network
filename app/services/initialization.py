# backend/app/services/initialization.py
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from ..config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
client = AsyncIOMotorClient(settings.mongodb_url)
db = client[settings.database_name]

async def initialize_sample_data():
    """Initialize sample data if not already present."""
    try:
        # Check if locations collection already has data
        locations_count = await db.locations.count_documents({})
        stats_count = await db.ats_stats.count_documents({})
        
        if locations_count > 0 and stats_count > 0:
            logger.info("Data already initialized")
            return

        logger.info("Starting data initialization")
        
        # Create indices for better query performance
        await db.locations.create_index([("name", 1)], unique=True)
        await db.locations.create_index([("lat", 1), ("lng", 1)])
        await db.ats_stats.create_index([("location_id", 1)], unique=True)

        logger.info("Created database indexes")
        logger.info("Data initialization completed successfully")
        
    except Exception as e:
        logger.error(f"Error during data initialization: {str(e)}")
        raise