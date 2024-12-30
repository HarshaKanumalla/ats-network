# backend/app/services/document.py
import aiofiles
import os
from fastapi import UploadFile, HTTPException
from pathlib import Path

UPLOAD_DIR = Path("uploads/documents")
ALLOWED_EXTENSIONS = {'.pdf', '.doc', '.docx'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

class DocumentService:
    def __init__(self):
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    async def process_upload(self, file: UploadFile, user_id: str) -> str:
        try:
            if not self._is_valid_file_type(file.filename):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid file type. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
                )

            safe_filename = self._generate_safe_filename(file.filename, user_id)
            file_path = UPLOAD_DIR / safe_filename

            async with aiofiles.open(file_path, 'wb') as out_file:
                while content := await file.read(1024 * 1024):  # Read in 1MB chunks
                    await out_file.write(content)

            return f"/documents/{safe_filename}"
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error processing file {file.filename}: {str(e)}"
            )

document_service = DocumentService()