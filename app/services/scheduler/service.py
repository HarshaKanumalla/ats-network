# backend/app/services/scheduler/service.py

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
import logging
import asyncio
import aiocron
from croniter import croniter
from bson import ObjectId

from ...core.exceptions import SchedulerError
from ...database import db_manager
from ...config import get_settings
from ...services.notification.notification_service import notification_service

logger = logging.getLogger(__name__)
settings = get_settings()

class TaskSchedulerService:
    """Enhanced service for managing scheduled tasks and background jobs."""
    
    def __init__(self):
        """Initialize task scheduler with enhanced capabilities."""
        self.active_tasks: Dict[str, Dict[str, Any]] = {}
        self.scheduled_jobs: Dict[str, aiocron.Cron] = {}
        
        # Task execution settings
        self.execution_settings = {
            'max_concurrent_tasks': 10,
            'task_timeout': 1800,        # 30 minutes
            'retry_attempts': 3,
            'retry_delay': 300,          # 5 minutes
            'maintenance_window': {
                'start': '01:00',         # 1 AM
                'end': '05:00'            # 5 AM
            }
        }
        
        # System maintenance tasks
        self.maintenance_tasks = {
            'database_backup': '0 1 * * *',         # Daily at 1 AM
            'document_cleanup': '0 2 * * *',        # Daily at 2 AM
            'analytics_update': '0 */4 * * *',      # Every 4 hours
            'system_health_check': '*/30 * * * *',  # Every 30 minutes
            'equipment_check': '0 6 * * *',         # Daily at 6 AM
            'expiry_notifications': '0 9 * * *'     # Daily at 9 AM
        }
        
        # Task prioritization
        self.task_priorities = {
            'system_critical': 0,    # Highest priority
            'maintenance': 1,
            'reporting': 2,
            'notification': 3,
            'cleanup': 4             # Lowest priority
        }
        
        logger.info("Task scheduler service initialized")

    async def start_scheduler(self) -> None:
        """Initialize and start the task scheduler with system tasks."""
        try:
            # Initialize system maintenance tasks
            for task_name, cron_expression in self.maintenance_tasks.items():
                await self.schedule_task(
                    task_name=task_name,
                    cron_expression=cron_expression,
                    task_function=getattr(self, f"_handle_{task_name}"),
                    priority='system_critical'
                )
            
            # Start task monitoring
            asyncio.create_task(self._monitor_tasks())
            
            logger.info("Task scheduler started successfully")
            
        except Exception as e:
            logger.error(f"Scheduler initialization error: {str(e)}")
            raise SchedulerError("Failed to start task scheduler")

    async def schedule_task(
        self,
        task_name: str,
        cron_expression: str,
        task_function: Callable,
        priority: str = 'maintenance',
        task_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """Schedule a new task with proper validation."""
        try:
            # Validate cron expression
            if not croniter.is_valid(cron_expression):
                raise SchedulerError("Invalid cron expression")
            
            # Generate task ID
            task_id = f"{task_name}_{datetime.utcnow().timestamp()}"
            
            # Create task record
            task_record = {
                "task_id": task_id,
                "task_name": task_name,
                "cron_expression": cron_expression,
                "priority": priority,
                "task_data": task_data,
                "status": "scheduled",
                "created_at": datetime.utcnow(),
                "next_run": croniter(
                    cron_expression,
                    datetime.utcnow()
                ).get_next(datetime),
                "last_run": None,
                "last_status": None,
                "retry_count": 0
            }
            
            # Store task record
            await db_manager.execute_query(
                collection="scheduled_tasks",
                operation="insert_one",
                query=task_record
            )
            
            # Schedule task execution
            self.scheduled_jobs[task_id] = aiocron.crontab(
                cron_expression,
                func=self._execute_task,
                args=(task_id, task_function, task_data),
                start=True
            )
            
            logger.info(f"Scheduled task: {task_name} with ID: {task_id}")
            return task_id
            
        except Exception as e:
            logger.error(f"Task scheduling error: {str(e)}")
            raise SchedulerError(f"Failed to schedule task: {str(e)}")

    async def _execute_task(
        self,
        task_id: str,
        task_function: Callable,
        task_data: Optional[Dict[str, Any]] = None
    ) -> None:
        """Execute scheduled task with comprehensive error handling."""
        try:
            # Update task status
            await self._update_task_status(task_id, "running")
            
            # Execute task with timeout
            async with asyncio.timeout(self.execution_settings['task_timeout']):
                result = await task_function(task_data)
            
            # Handle successful execution
            await self._handle_task_completion(task_id, result)
            
        except asyncio.TimeoutError:
            await self._handle_task_failure(
                task_id,
                "Task execution timed out"
            )
        except Exception as e:
            await self._handle_task_failure(
                task_id,
                str(e)
            )

    async def _handle_task_failure(
        self,
        task_id: str,
        error_message: str
    ) -> None:
        """Handle task failure with retry mechanism."""
        try:
            task_record = await db_manager.execute_query(
                collection="scheduled_tasks",
                operation="find_one",
                query={"task_id": task_id}
            )
            
            if task_record["retry_count"] < self.execution_settings['retry_attempts']:
                # Schedule retry
                await asyncio.sleep(self.execution_settings['retry_delay'])
                await self._update_task_status(
                    task_id,
                    "retry",
                    {
                        "retry_count": task_record["retry_count"] + 1,
                        "last_error": error_message
                    }
                )
                
                # Retry task execution
                await self._execute_task(
                    task_id,
                    self.scheduled_jobs[task_id].func,
                    task_record["task_data"]
                )
            else:
                # Mark task as failed
                await self._update_task_status(
                    task_id,
                    "failed",
                    {"last_error": error_message}
                )
                
                # Notify about task failure
                await self._notify_task_failure(task_id, error_message)
                
        except Exception as e:
            logger.error(f"Task failure handling error: {str(e)}")

    async def _handle_database_backup(
        self,
        data: Optional[Dict[str, Any]] = None
    ) -> None:
        """Handle automated database backup."""
        try:
            # Implementation for database backup
            pass
        except Exception as e:
            logger.error(f"Database backup error: {str(e)}")
            raise SchedulerError("Failed to perform database backup")

    async def _handle_document_cleanup(
        self,
        data: Optional[Dict[str, Any]] = None
    ) -> None:
        """Handle temporary document cleanup."""
        try:
            # Implementation for document cleanup
            pass
        except Exception as e:
            logger.error(f"Document cleanup error: {str(e)}")
            raise SchedulerError("Failed to cleanup documents")

    async def _handle_analytics_update(
        self,
        data: Optional[Dict[str, Any]] = None
    ) -> None:
        """Handle analytics data update."""
        try:
            # Implementation for analytics update
            pass
        except Exception as e:
            logger.error(f"Analytics update error: {str(e)}")
            raise SchedulerError("Failed to update analytics")

    async def _handle_system_health_check(
        self,
        data: Optional[Dict[str, Any]] = None
    ) -> None:
        """Handle system health monitoring."""
        try:
            # Implementation for health check
            pass
        except Exception as e:
            logger.error(f"Health check error: {str(e)}")
            raise SchedulerError("Failed to perform health check")

    async def _handle_equipment_check(
        self,
        data: Optional[Dict[str, Any]] = None
    ) -> None:
        """Handle equipment monitoring and maintenance checks."""
        try:
            # Implementation for equipment check
            pass
        except Exception as e:
            logger.error(f"Equipment check error: {str(e)}")
            raise SchedulerError("Failed to check equipment")

    async def _handle_expiry_notifications(
        self,
        data: Optional[Dict[str, Any]] = None
    ) -> None:
        """Handle document and certificate expiry notifications."""
        try:
            # Implementation for expiry notifications
            pass
        except Exception as e:
            logger.error(f"Expiry notification error: {str(e)}")
            raise SchedulerError("Failed to send expiry notifications")

# Initialize task scheduler
task_scheduler = TaskSchedulerService()