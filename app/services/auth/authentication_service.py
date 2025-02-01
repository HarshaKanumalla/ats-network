# backend/app/services/auth/authentication_service.py

from datetime import datetime
from typing import Dict, Any, Tuple, Optional
import logging
from fastapi import HTTPException, status
from bson import ObjectId

from ...core.security import SecurityManager
from ...core.auth.token import TokenService
from ...services.email.email_service import EmailService
from ...services.s3.s3_service import S3Service
from ...database import get_database, database_transaction
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class AuthenticationService:
    def __init__(self):
        self.security = SecurityManager()
        self.token_service = TokenService()
        self.email_service = EmailService()
        self.s3_service = S3Service()

    async def register_user(self, user_data: Dict[str, Any], documents: Dict[str, Any]) -> Dict[str, Any]:
        """Handle user registration with document verification and email notification."""
        async with database_transaction() as session:
            try:
                db = await get_database()

                # Email validation
                if await db.users.find_one({"email": user_data["email"]}):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Email address already registered"
                    )

                # Process and store documents in S3
                document_urls = await self._process_registration_documents(
                    user_data["email"],
                    documents
                )

                # Create user record
                user_record = {
                    "email": user_data["email"],
                    "passwordHash": self.security.get_password_hash(user_data["password"]),
                    "firstName": user_data["firstName"],
                    "lastName": user_data["lastName"],
                    "phoneNumber": user_data["phoneNumber"],
                    "role": "pending",
                    "status": "pending",
                    "atsCenter": {
                        "name": user_data["centerName"],
                        "address": user_data["address"],
                        "city": user_data["city"],
                        "district": user_data["district"],
                        "state": user_data["state"],
                        "pinCode": user_data["pinCode"],
                        "coordinates": None  # Will be updated after verification
                    },
                    "documents": document_urls,
                    "isActive": True,
                    "isVerified": False,
                    "createdAt": datetime.utcnow(),
                    "updatedAt": datetime.utcnow()
                }

                # Insert user with transaction
                result = await db.users.insert_one(user_record, session=session)
                user_record["_id"] = result.inserted_id

                # Send registration pending email
                await self.email_service.send_registration_pending(
                    email=user_data["email"],
                    name=f"{user_data['firstName']} {user_data['lastName']}",
                    center_name=user_data["centerName"]
                )

                logger.info(f"User registered successfully: {user_data['email']}")
                return {"id": str(result.inserted_id), "status": "pending"}

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Registration error: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Registration failed"
                )

    async def authenticate_user(self, email: str, password: str) -> Dict[str, Any]:
        """Authenticate user and generate access tokens."""
        try:
            db = await get_database()

            # Find user and verify credentials
            user = await db.users.find_one({"email": email})
            if not user or not self.security.verify_password(password, user["passwordHash"]):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid credentials"
                )

            # Check user status
            if not user["isActive"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account is inactive"
                )

            if user["status"] != "approved":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account pending approval"
                )

            # Generate tokens
            access_token, refresh_token = await self.token_service.create_tokens(
                str(user["_id"]),
                {
                    "role": user["role"],
                    "center_id": str(user["atsCenter"]["_id"]) if "atsCenter" in user else None
                }
            )

            # Update last login
            await db.users.update_one(
                {"_id": user["_id"]},
                {
                    "$set": {
                        "lastLogin": datetime.utcnow(),
                        "updatedAt": datetime.utcnow()
                    }
                }
            )

            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "user": self._format_user_response(user)
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication failed"
            )

    async def _process_registration_documents(
        self,
        email: str,
        documents: Dict[str, Any]
    ) -> Dict[str, str]:
        """Process and store registration documents securely."""
        try:
            document_urls = {}
            for doc_type, file in documents.items():
                url = await self.s3_service.upload_document(
                    file=file,
                    folder=f"users/{email}/registration",
                    metadata={
                        "user_email": email,
                        "document_type": doc_type
                    }
                )
                document_urls[doc_type] = url
            return document_urls

        except Exception as e:
            logger.error(f"Document processing error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to process documents"
            )

    def _format_user_response(self, user: Dict[str, Any]) -> Dict[str, Any]:
        """Format user data for response."""
        return {
            "id": str(user["_id"]),
            "email": user["email"],
            "firstName": user["firstName"],
            "lastName": user["lastName"],
            "role": user["role"],
            "status": user["status"],
            "atsCenter": user.get("atsCenter"),
            "lastLogin": user.get("lastLogin")
        }

# Initialize authentication service
auth_service = AuthenticationService()