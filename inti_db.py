from pymongo import MongoClient
from datetime import datetime
from passlib.context import CryptContext

# MongoDB connection
client = MongoClient('mongodb://localhost:27017/')
db = client['ats_network']

# Password hashing setup
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Admin user data
admin_user = {
    "email": "atsnetwork15@gmail.com",
    "hashed_password": pwd_context.hash("Admin@123"),
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

# Check if admin user exists
existing_user = db.users.find_one({"email": admin_user["email"]})

if existing_user:
    # Update existing user
    db.users.update_one(
        {"email": admin_user["email"]},
        {"$set": admin_user}
    )
    print("Admin user updated successfully")
else:
    # Create new admin user
    db.users.insert_one(admin_user)
    print("Admin user created successfully")