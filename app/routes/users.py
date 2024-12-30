# backend/app/routes/users.py
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from typing import List
from typing_extensions import Annotated

from ..models.user import User, UserUpdate
from ..services.database import get_user_by_id, update_user, store_document
from ..services.document import document_service
from ..utils.security import get_current_user

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
    updated_user = await update_user(current_user.id, user_update.dict(exclude_unset=True))
    return updated_user

@router.post("/me/documents")
async def upload_documents(
    current_user: Annotated[User, Depends(get_current_user)],
    files: List[UploadFile] = File(...)
):
    if len(files) > 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 5 documents allowed"
        )
    
    uploaded_documents = []
    for file in files:
        try:
            document_url = await document_service.process_upload(file, current_user.id)
            stored_url = await store_document(current_user.id, document_url)
            uploaded_documents.append(stored_url)
        except HTTPException as e:
            raise e
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error processing file {file.filename}: {str(e)}"
            )
    
    return {"uploaded_documents": uploaded_documents}