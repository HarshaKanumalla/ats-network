from typing import Any, Dict, Optional, Callable
import logging
import asyncio
from datetime import datetime
import redis
from rq import Queue, Retry
from rq.job import Job

from ...core.exceptions import QueueError
from ...config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class QueueService:
    def __init__(self):
        self.redis = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            decode_responses=True
        )
        
        # Initialize queues with priorities
        self.queues = {
            'high': Queue('high', connection=self.redis),
            'default': Queue('default', connection=self.redis),
            'low': Queue('low', connection=self.redis)
        }
        
        # Task registration
        self.task_registry = {}
        
        logger.info("Queue service initialized")

    async def enqueue_task(
        self,
        task_name: str,
        args: Optional[tuple] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        priority: str = 'default',
        timeout: Optional[int] = None,
        retry: bool = True
    ) -> str:
        """Enqueue a task with priority support."""
        try:
            if task_name not in self.task_registry:
                raise QueueError(f"Task {task_name} not registered")
                
            queue = self.queues.get(priority, self.queues['default'])
            
            job = queue.enqueue(
                self.task_registry[task_name],
                args=args or (),
                kwargs=kwargs or {},
                timeout=timeout,
                retry=Retry(max=3) if retry else None
            )
            
            # Store job metadata
            await self._update_task_metadata(job.id, "queued")
            
            logger.info(f"Task {job.id} enqueued with priority {priority}")
            return job.id
            
        except Exception as e:
            logger.error(f"Task enqueue error: {str(e)}")
            raise QueueError(f"Failed to enqueue task: {str(e)}")

    async def register_task(
        self,
        task_name: str,
        task_func: Callable,
        timeout: Optional[int] = None
    ) -> None:
        """Register a task function."""
        try:
            if not callable(task_func):
                raise QueueError(f"Task function for {task_name} is not callable")
            
            self.task_registry[task_name] = task_func
            logger.info(f"Registered task: {task_name}")
            
        except Exception as e:
            logger.error(f"Task registration error: {str(e)}")
            raise QueueError(f"Failed to register task: {str(e)}")

    async def get_task_status(self, job_id: str) -> Dict[str, Any]:
        """Get task execution status."""
        try:
            job = Job.fetch(job_id, connection=self.redis)
            if not job:
                raise QueueError(f"Job with ID {job_id} not found")
            
            return {
                "id": job_id,
                "status": job.get_status(),
                "result": job.result,
                "created_at": job.created_at.isoformat(),
                "ended_at": job.ended_at.isoformat() if job.ended_at else None,
                "execution_time": job.execution_time,
                "metadata": await self.redis.hgetall(f"task:{job_id}")
            }
            
        except Exception as e:
            logger.error(f"Task status error: {str(e)}")
            raise QueueError(f"Failed to get task status: {str(e)}")

    async def cancel_task(self, job_id: str) -> None:
        """Cancel a queued or running task."""
        try:
            job = Job.fetch(job_id, connection=self.redis)
            if job.get_status() in ["finished", "failed"]:
                raise QueueError(f"Cannot cancel task {job_id} as it is already {job.get_status()}")
            
            job.cancel()
            
            await self._update_task_metadata(job_id, "cancelled")
            logger.info(f"Cancelled task: {job_id}")
            
        except Exception as e:
            logger.error(f"Task cancellation error: {str(e)}")
            raise QueueError(f"Failed to cancel task: {str(e)}")

    async def _update_task_metadata(self, job_id: str, status: str) -> None:
        """Update task metadata in Redis."""
        try:
            await self.redis.hset(
                f"task:{job_id}",
                mapping={
                    "status": status,
                    "updated_at": datetime.utcnow().isoformat()
                }
            )
        except Exception as e:
            logger.error(f"Task metadata update error: {str(e)}")

queue_service = QueueService()