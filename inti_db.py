import os
import logging
from pymongo import MongoClient, errors
from datetime import datetime
from passlib.context import CryptContext
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# MongoDB connection
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DATABASE_NAME = os.getenv("DATABASE_NAME", "ats_network")

try:
    client = MongoClient(MONGO_URI)
    db = client[DATABASE_NAME]
    logger.info("Connected to MongoDB successfully")
except errors.ConnectionError as e:
    logger.error(f"Failed to connect to MongoDB: {str(e)}")
    exit(1)

# Password hashing setup
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Admin user data
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "atsnetwork15@gmail.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin@123")

admin_user = {
    "email": ADMIN_EMAIL,
    "hashed_password": pwd_context.hash(ADMIN_PASSWORD),
    "full_name": "Admin User",
    "ats_address": "Admin Office",
    "city": "Admin City",
    "district": "Admin District",
    "state": "Admin State",
    "pin_code": "000000",
    "role": "admin",
    "status": "approved",
    "is_active": True,
    "is_verified": True,
    "created_at": datetime.utcnow(),
    "updated_at": datetime.utcnow(),
    "documents": []
}

def ensure_email_index():
    """Ensure the email field is indexed in the users collection."""
    try:
        db.users.create_index("email", unique=True)
        logger.info("Ensured email index on users collection")
    except Exception as e:
        logger.error(f"Failed to create email index: {str(e)}")

def initialize_admin_user():
    """Initialize the admin user in the database."""
    try:
        existing_user = db.users.find_one({"email": admin_user["email"]})
        if existing_user:
            # Check if the password needs to be updated
            if not pwd_context.verify(ADMIN_PASSWORD, existing_user["hashed_password"]):
                admin_user["hashed_password"] = pwd_context.hash(ADMIN_PASSWORD)
                admin_user["updated_at"] = datetime.utcnow()
                db.users.update_one({"email": admin_user["email"]}, {"$set": admin_user})
                logger.info("Admin user updated successfully")
            else:
                logger.info("Admin user already exists and is up-to-date")
        else:
            # Create new admin user
            db.users.insert_one(admin_user)
            logger.info("Admin user created successfully")
    except Exception as e:
        logger.error(f"Error initializing admin user: {str(e)}")

if __name__ == "__main__":
    ensure_email_index()
    initialize_admin_user()