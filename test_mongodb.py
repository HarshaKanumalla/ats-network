# test_mongodb.py
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio

async def test_connection():
    client = AsyncIOMotorClient('mongodb://localhost:27017')
    db = client.ats_network
    
    # Test database connection
    try:
        # The ismaster command is cheap and does not require auth
        await client.admin.command('ismaster')
        print("MongoDB connection successful!")
        
        # Test database access
        await db.users.insert_one({
            'test': 'data'
        })
        print("Successfully inserted test document!")
        
        # Clean up test data
        await db.users.delete_one({'test': 'data'})
        print("Successfully cleaned up test data!")
        
    except Exception as e:
        print(f"MongoDB connection failed: {e}")

# Run the test
asyncio.run(test_connection())