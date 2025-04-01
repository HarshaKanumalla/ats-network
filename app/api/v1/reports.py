# backend/app/api/v1/reports.py

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime, timedelta
from pydantic import BaseModel, EmailStr, Field

from ...core.auth.permissions import RolePermission, require_permission
from ...core.security import get_current_user
from ...services.report.service import report_service
from ...services.notification.service import notification_service
from ...services.s3.service import s3_service
from ...models.report import (
    ReportRequest,
    ReportResponse,
    ReportSchedule,
    ReportTemplate
)
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()

class ShareReportRequest(BaseModel):
    recipients: List[EmailStr]
    message: Optional[str] = Field(None, max_length=500, description="Optional sharing message")

@router.post("/generate", response_model=ReportResponse)
async def generate_report(
    report_request: ReportRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.GENERATE_REPORTS))
) -> ReportResponse:
    """Generate a custom report based on specified parameters."""
    try:
        # Validate report parameters
        await report_service.validate_report_parameters(
            report_type=report_request.report_type,
            parameters=report_request.parameters
        )

        # Check access permissions for report type
        if not await report_service.can_access_report_type(
            user=current_user,
            report_type=report_request.report_type
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to generate this report type"
            )

        # Initialize report generation
        report_job = await report_service.initialize_report_job(
            report_type=report_request.report_type,
            parameters=report_request.parameters,
            format=report_request.format,
            user_id=str(current_user.id)
        )

        # Queue report generation
        background_tasks.add_task(
            report_service.generate_report,
            report_job_id=str(report_job.id)
        )

        logger.info(f"Report generation initiated for user {current_user.id}")

        return ReportResponse(
            status="success",
            message="Report generation initiated successfully",
            data={
                "job_id": str(report_job.id),
                "estimated_completion": report_job.estimated_completion
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Report generation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate report generation"
        )

@router.get("/status/{job_id}", response_model=ReportResponse)
async def get_report_status(
    job_id: str,
    current_user=Depends(get_current_user)
) -> ReportResponse:
    """Get status of a report generation job."""
    try:
        status = await report_service.get_report_status(
            job_id=job_id,
            user_id=str(current_user.id)
        )

        logger.info(f"Report status retrieved successfully for job ID: {job_id[:5]}***")
        return ReportResponse(
            status="success",
            message="Report status retrieved successfully",
            data=status
        )

    except Exception as e:
        logger.error(f"Report status retrieval error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve report status"
        )

@router.post("/schedule", response_model=ReportResponse)
async def schedule_report(
    schedule: ReportSchedule,
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.SCHEDULE_REPORTS))
) -> ReportResponse:
    """Schedule automated report generation."""
    try:
        scheduled_report = await report_service.schedule_report(
            schedule=schedule,
            user_id=str(current_user.id)
        )

        logger.info(f"Report scheduled successfully by user {current_user.id}")
        return ReportResponse(
            status="success",
            message="Report scheduled successfully",
            data=scheduled_report
        )

    except Exception as e:
        logger.error(f"Report scheduling error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to schedule report"
        )

@router.get("/templates", response_model=List[ReportTemplate])
async def get_report_templates(
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.VIEW_REPORT_TEMPLATES))
) -> List[ReportTemplate]:
    """Get available report templates based on user role."""
    try:
        templates = await report_service.get_available_templates(
            user_role=current_user.role
        )

        logger.info(f"Report templates retrieved successfully for user {current_user.id}")
        return templates

    except Exception as e:
        logger.error(f"Template retrieval error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve report templates"
        )

@router.post("/templates", response_model=ReportTemplate)
async def create_report_template(
    template: ReportTemplate,
    current_user=Depends(get_current_user),
    _=Depends(require_permission(RolePermission.MANAGE_REPORT_TEMPLATES))
) -> ReportTemplate:
    """Create a new report template."""
    try:
        created_template = await report_service.create_template(
            template=template,
            created_by=str(current_user.id)
        )

        logger.info(f"Report template created successfully by user {current_user.id}")
        return created_template

    except Exception as e:
        logger.error(f"Template creation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create report template"
        )

@router.get("/history", response_model=List[ReportResponse])
async def get_report_history(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    report_type: Optional[str] = None,
    current_user=Depends(get_current_user)
) -> List[ReportResponse]:
    """Get user's report generation history."""
    try:
        history = await report_service.get_report_history(
            user_id=str(current_user.id),
            start_date=start_date,
            end_date=end_date,
            report_type=report_type
        )

        logger.info(f"Report history retrieved successfully for user {current_user.id}")
        return [
            ReportResponse(
                status="success",
                message="Report retrieved successfully",
                data=report
            ) for report in history
        ]

    except Exception as e:
        logger.error(f"Report history retrieval error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve report history"
        )

@router.get("/download/{report_id}")
async def download_report(
    report_id: str,
    current_user=Depends(get_current_user)
) -> Dict[str, str]:
    """Get download URL for a generated report."""
    try:
        # Verify report access
        if not await report_service.can_access_report(
            user_id=str(current_user.id),
            report_id=report_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this report"
            )

        download_url = await report_service.get_report_download_url(report_id)

        logger.info(f"Download URL generated successfully for report ID: {report_id[:5]}***")
        return {
            "status": "success",
            "message": "Download URL generated successfully",
            "url": download_url
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Download URL generation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate download URL"
        )

@router.post("/share/{report_id}")
async def share_report(
    report_id: str,
    share_request: ShareReportRequest,
    current_user=Depends(get_current_user)
) -> Dict[str, Any]:
    """Share a generated report with other users."""
    try:
        # Verify report access
        if not await report_service.can_share_report(
            user_id=str(current_user.id),
            report_id=report_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to share this report"
            )

        share_results = await report_service.share_report(
            report_id=report_id,
            recipients=share_request.recipients,
            message=share_request.message,
            shared_by=str(current_user.id)
        )

        logger.info(f"Report shared successfully for report ID: {report_id[:5]}***")
        return {
            "status": "success",
            "message": "Report shared successfully",
            "data": share_results
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Report sharing error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to share report"
        )