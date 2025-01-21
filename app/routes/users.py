# backend/app/routes/users.py

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from typing import List
from typing_extensions import Annotated

from ..models.user import User, UserUpdate
from ..services.database import (
    get_user_by_id,
    update_user,
    store_document,
    get_user_documents,
    remove_document
)
from ..services.auth import get_current_user
from ..services.document import document_service

router = APIRouter()

@router.get("/me", response_model=User)
async def get_current_user_info(
    current_user: Annotated[User, Depends(get_current_user)]
):
    return current_user

@router.put("/me", response_model=User)
async def update_user_info(
    user_update: UserUpdate,
    current_user: Annotated[User, Depends(get_current_user)]
):
    updated_user = await update_user(str(current_user.id), user_update.dict(exclude_unset=True))
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user information"
        )
    return updated_user

@router.post("/me/documents")
async def upload_documents(
    current_user: Annotated[User, Depends(get_current_user)],
    files: List[UploadFile] = File(...)
):
    if len(files) > 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 5 documents allowed per upload"
        )
    
    uploaded_documents = []
    for file in files:
        try:
            document_url = await document_service.process_upload(file, str(current_user.id))
            doc_id = await store_document(str(current_user.id), document_url)
            if doc_id:
                uploaded_documents.append({"id": doc_id, "url": document_url})
        except HTTPException as e:
            raise e
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error processing file {file.filename}: {str(e)}"
            )
    
    return {"uploaded_documents": uploaded_documents}

@router.get("/me/documents")
async def get_my_documents(
    current_user: Annotated[User, Depends(get_current_user)]
):
    documents = await get_user_documents(str(current_user.id))
    return {"documents": documents}

@router.delete("/me/documents/{document_id}")
async def delete_document(
    document_id: str,
    current_user: Annotated[User, Depends(get_current_user)]
):
    success = await remove_document(str(current_user.id), document_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found or already deleted"
        )
    return {"message": "Document deleted successfully"}