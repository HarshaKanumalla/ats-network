"""User management routes handling user-related operations."""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from typing import List, Dict, Any
from fastapi.responses import JSONResponse
import logging

from ..models.user import User, UserUpdate, UserResponse
from ..services.auth import get_current_user
from ..services.database import update_user, get_user_documents, store_document
from ..services.document import document_service

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/me", response_model=User)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
) -> User:
    """Retrieve the current user's profile information."""
    return current_user

@router.put("/me", response_model=UserResponse)
async def update_user_info(
    update_data: UserUpdate,
    current_user: User = Depends(get_current_user)
) -> UserResponse:
    """Update the current user's profile information."""
    try:
        updated_user = await update_user(
            str(current_user.id),
            update_data.dict(exclude_unset=True)
        )
        
        if not updated_user:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update user information"
            )

        return UserResponse(
            status="success",
            message="Profile updated successfully",
            data=updated_user
        )

    except Exception as e:
        logger.error(f"Error updating user information: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Profile update failed"
        )

@router.post("/me/documents")
async def upload_documents(
    current_user: User = Depends(get_current_user),
    files: List[UploadFile] = File(...)
) -> JSONResponse:
    """Upload user documents to the system."""
    try:
        if len(files) > 5:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Maximum 5 documents allowed per upload"
            )

        uploaded_documents = []
        for file in files:
            document_url = await document_service.process_upload(
                file,
                str(current_user.id)
            )
            doc_id = await store_document(
                str(current_user.id),
                document_url
            )
            uploaded_documents.append({
                "id": doc_id,
                "url": document_url
            })

        return JSONResponse(
            content={
                "status": "success",
                "message": f"Successfully uploaded {len(files)} documents",
                "documents": uploaded_documents
            },
            status_code=status.HTTP_200_OK
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Document upload error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process document upload"
        )

@router.get("/me/documents")
async def get_user_documents_info(
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Retrieve information about user's uploaded documents."""
    try:
        documents = await get_user_documents(str(current_user.id))
        return {
            "status": "success",
            "total_documents": len(documents),
            "documents": documents
        }
    except Exception as e:
        logger.error(f"Error retrieving user documents: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve documents"
        )