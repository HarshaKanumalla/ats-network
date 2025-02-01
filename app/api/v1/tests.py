from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, WebSocket
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime
import asyncio
from bson import ObjectId

from ...core.auth.permissions import RolePermission, require_permission, check_test_access
from ...core.security import get_current_user, verify_websocket_token
from ...services.test.test_service import test_service
from ...services.test.monitor import test_monitor
from ...services.test.results_service import test_results_service
from ...services.websocket.manager import websocket_manager
from ...services.s3.service import s3_service
from ...services.notification.service import notification_service
from ...models.test import (
    TestSession,
    TestResult,
    TestType,
    TestResponse
)
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()

@router.post("/sessions", response_model=TestResponse)
async def create_test_session(
    vehicle_id: str,
    center_id: str,
    current_user = Depends(get_current_user),
    _=Depends(require_permission(RolePermission.CONDUCT_TESTS))
) -> TestResponse:
    """Initialize a new vehicle test session.
    
    Args:
        vehicle_id: ID of vehicle to test
        center_id: ID of testing center
        current_user: Authenticated user
        
    Returns:
        Created test session information
        
    Raises:
        HTTPException: If creation fails or validation errors occur
    """
    try:
        # Verify test prerequisites
        if not await test_service.verify_test_prerequisites(
            vehicle_id=vehicle_id,
            center_id=center_id,
            operator_id=str(current_user.id)
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Test prerequisites not met"
            )

        # Create test session
        session = await test_service.create_test_session(
            vehicle_id=vehicle_id,
            center_id=center_id,
            operator_id=str(current_user.id)
        )

        # Initialize real-time monitoring
        await test_monitor.start_monitoring_session(
            session_id=str(session.id),
            vehicle_id=vehicle_id,
            center_id=center_id,
            operator_id=str(current_user.id)
        )

        # Send notifications
        await notification_service.notify_test_session_created(
            session_id=str(session.id),
            vehicle_id=vehicle_id,
            center_id=center_id
        )

        logger.info(f"Created test session: {session.session_code}")
        return TestResponse(
            status="success",
            message="Test session created successfully",
            data=session
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session creation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create test session"
        )

@router.websocket("/ws/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    token: str
):
    """WebSocket endpoint for real-time test data streaming.
    
    Args:
        websocket: WebSocket connection
        session_id: ID of test session
        token: Authentication token
    """
    try:
        # Verify token and permissions
        current_user = await verify_websocket_token(token)
        if not current_user:
            await websocket.close(code=4001)
            logger.warning(f"Invalid token for WebSocket connection: {session_id}")
            return

        # Verify session access
        if not await check_test_access(current_user, session_id):
            await websocket.close(code=4003)
            logger.warning(f"Unauthorized session access attempt: {session_id}")
            return

        # Accept connection
        await websocket.accept()
        client_id = f"client_{str(current_user.id)}"
        
        # Connect to test monitor
        await test_monitor.connect_client(
            websocket=websocket,
            session_id=session_id,
            client_id=client_id,
            user=current_user
        )

        try:
            while True:
                # Process incoming messages
                data = await websocket.receive_json()
                
                # Handle different message types
                message_type = data.get("type")
                
                if message_type == "ping":
                    await websocket.send_json({"type": "pong"})
                    
                elif message_type == "test_data":
                    # Process and validate test data
                    processed_data = await test_monitor.process_test_data(
                        session_id=session_id,
                        test_type=data.get("test_type"),
                        raw_data=data.get("data", {})
                    )
                    
                    # Broadcast processed data
                    await websocket_manager.broadcast_test_data(
                        session_id=session_id,
                        test_type=data.get("test_type"),
                        data=processed_data
                    )
                    
                elif message_type == "status_update":
                    # Update session status
                    await test_monitor.update_session_status(
                        session_id=session_id,
                        status=data.get("status"),
                        client_id=client_id
                    )

        except Exception as e:
            logger.error(f"WebSocket message processing error: {str(e)}")
            await websocket.send_json({
                "type": "error",
                "message": "Failed to process message"
            })

    except Exception as e:
        logger.error(f"WebSocket connection error: {str(e)}")
        await websocket.close(code=4000)
    
    finally:
        # Clean up connection
        await test_monitor.disconnect_client(
            session_id=session_id,
            client_id=client_id
        )

@router.post("/sessions/{session_id}/data", response_model=TestResponse)
async def update_test_data(
    session_id: str,
    test_type: TestType,
    data: Dict[str, Any],
    images: Optional[List[UploadFile]] = File(None),
    current_user = Depends(get_current_user),
    _=Depends(require_permission(RolePermission.CONDUCT_TESTS))
) -> TestResponse:
    """Update test measurement data.
    
    Args:
        session_id: ID of test session
        test_type: Type of test being performed
        data: Test measurement data
        images: Optional test images
        current_user: Authenticated user
        
    Returns:
        Updated test session information
        
    Raises:
        HTTPException: If update fails or validation errors occur
    """
    try:
        # Verify session access
        if not await check_test_access(current_user, session_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this test session"
            )

        # Process images if provided
        image_urls = []
        if images:
            for image in images:
                url = await s3_service.upload_document(
                    file=image,
                    folder=f"tests/{session_id}/{test_type}",
                    metadata={
                        "session_id": session_id,
                        "test_type": test_type,
                        "uploaded_by": str(current_user.id)
                    }
                )
                image_urls.append(url)

        # Add image URLs to test data
        if image_urls:
            data["images"] = image_urls

        # Process and validate test data
        updated_session = await test_service.update_test_data(
            session_id=session_id,
            test_type=test_type,
            data=data,
            updated_by=str(current_user.id)
        )

        return TestResponse(
            status="success",
            message="Test data updated successfully",
            data=updated_session
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Test data update error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update test data"
        )

@router.post("/sessions/{session_id}/complete", response_model=TestResponse)
async def complete_test_session(
    session_id: str,
    current_user = Depends(get_current_user),
    _=Depends(require_permission(RolePermission.CONDUCT_TESTS))
) -> TestResponse:
    """Complete a test session and generate final results.
    
    Args:
        session_id: ID of test session
        current_user: Authenticated user
        
    Returns:
        Completed test session information
        
    Raises:
        HTTPException: If completion fails
    """
    try:
        # Verify session access
        if not await check_test_access(current_user, session_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to complete this test session"
            )

        # Process final results
        session = await test_service.complete_test_session(
            session_id=session_id,
            completed_by=str(current_user.id)
        )

        # Generate test report
        report_url = await test_results_service.generate_test_report(
            session_id=session_id
        )

        # Send notifications
        await notification_service.notify_test_completion(
            session_id=session_id,
            report_url=report_url
        )

        # Update monitoring status
        await test_monitor.stop_monitoring_session(session_id)

        return TestResponse(
            status="success",
            message="Test session completed successfully",
            data={**session.dict(), "report_url": report_url}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Session completion error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete test session"
        )

@router.get("/sessions/{session_id}/status", response_model=Dict[str, Any])
async def get_session_status(
    session_id: str,
    current_user = Depends(get_current_user),
    _=Depends(require_permission(RolePermission.VIEW_TEST_STATUS))
) -> Dict[str, Any]:
    """Get current test session status and progress.
    
    Args:
        session_id: ID of test session
        current_user: Authenticated user
        
    Returns:
        Session status information
        
    Raises:
        HTTPException: If retrieval fails
    """
    try:
        # Verify session access
        if not await check_test_access(current_user, session_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view this test session"
            )

        status = await test_service.get_session_status(session_id)

        return {
            "status": "success",
            "message": "Session status retrieved successfully",
            "data": status
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Status retrieval error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve session status"
        )

@router.get("/vehicles/{vehicle_id}/history", response_model=List[TestResponse])
async def get_vehicle_test_history(
    vehicle_id: str,
    current_user = Depends(get_current_user),
    _=Depends(require_permission(RolePermission.VIEW_TEST_HISTORY))
) -> List[TestResponse]:
    """Get complete test history for a vehicle.
    
    Args:
        vehicle_id: ID of vehicle
        current_user: Authenticated user
        
    Returns:
        List of test sessions for vehicle
        
    Raises:
        HTTPException: If retrieval fails
    """
    try:
        # Get test history with role-based filtering
        sessions = await test_service.get_vehicle_test_history(
            vehicle_id=vehicle_id,
            user=current_user
        )

        return [
            TestResponse(
                status="success",
                message="Test session retrieved successfully",
                data=session
            ) for session in sessions
        ]

    except Exception as e:
        logger.error(f"Test history retrieval error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve test history"
        )