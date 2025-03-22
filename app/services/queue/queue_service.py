from typing import Any, Dict, Optional, Callable
import logging
import asyncio
from datetime import datetime
import json
import redis
from rq import Queue
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
                retry=retry
            )
            
            # Store job metadata
            await self.redis.hset(
                f"task:{job.id}",
                mapping={
                    "name": task_name,
                    "priority": priority,
                    "status": "queued",
                    "created_at": datetime.utcnow().isoformat()
                }
            )
            
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
            self.task_registry[task_name] = task_func
            logger.info(f"Registered task: {task_name}")
            
        except Exception as e:
            logger.error(f"Task registration error: {str(e)}")
            raise QueueError(f"Failed to register task: {str(e)}")

    async def get_task_status(self, job_id: str) -> Dict[str, Any]:
        """Get task execution status."""
        try:
            job = Job.fetch(job_id, connection=self.redis)
            
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
            job.cancel()
            
            await self.redis.hset(
                f"task:{job_id}",
                "status",
                "cancelled"
            )
            
            logger.info(f"Cancelled task: {job_id}")
            
        except Exception as e:
            logger.error(f"Task cancellation error: {str(e)}")
            raise QueueError(f"Failed to cancel task: {str(e)}")

queue_service = QueueService()