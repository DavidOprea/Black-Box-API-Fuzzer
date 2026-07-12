from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from celery.result import AsyncResult
from typing import Optional
import logging
import os
from datetime import datetime
import requests
import redis

from .schemas import (
    FuzzRequest, FuzzResponse, StatusResponse, TaskStatus, CrashResult
)
from .worker import fuzz_api_task, celery_app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Black-Box Fuzzer API",
    description="API fuzzing service for detecting 5xx errors",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Redis client for state management
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
redis_client = redis.from_url(redis_url, decode_responses=True)

@app.get("/health")
async def health():
    """Health check endpoint."""
    try:
        redis_client.ping()
        return {"status": "ok", "redis": "connected"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "degraded", "error": str(e)}, 503

@app.post("/fuzz", response_model=FuzzResponse)
async def submit_fuzz_job(request: FuzzRequest):
    """
    Submit a fuzzing job.
    - Validates OpenAPI URL
    - Enqueues Celery task
    - Returns task_id for polling
    """
    try:
        logger.info(f"New fuzz request for {request.target_openapi_url}")

        # Enqueue task
        task = fuzz_api_task.apply_async(
            args=[
                str(request.target_openapi_url),
                request.api_key_header,
                request.api_key_value,
            ],
            expires=300,  # 5-minute expiration
        )

        logger.info(f"Task enqueued: {task.id}")

        return FuzzResponse(
            task_id=task.id,
            status=TaskStatus.PENDING,
            message=f"Fuzzing job {task.id} queued. Start polling /status/{task.id}"
        )

    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error submitting job: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to submit job")

@app.get("/status/{task_id}", response_model=StatusResponse)
async def get_status(task_id: str):
    """
    Poll job status.
    Returns real-time progress, crashes found, and cURL commands.
    """
    try:
        result = AsyncResult(task_id, app=celery_app)

        if result.state == 'PENDING':
            return StatusResponse(
                task_id=task_id,
                status=TaskStatus.PENDING,
                progress_percent=0,
                total_tests_run=0,
                total_crashes=0,
                message="Job pending in queue"
            )

        elif result.state == 'STARTED':
            return StatusResponse(
                task_id=task_id,
                status=TaskStatus.RUNNING,
                progress_percent=0,
                total_tests_run=0,
                total_crashes=0,
                message="Fuzzing in progress"
            )

        elif result.state == 'SUCCESS':
            # Safely handle the data; if result.result is None, use an empty dict
            data = result.result if result.result is not None else {}
            return StatusResponse(
                task_id=task_id,
                status=TaskStatus.SUCCESS,
                progress_percent=100,
                total_tests_run=data.get('total_tests', 0),
                total_crashes=data.get('total_crashes', 0),
                crashes=[CrashResult(**c) for c in data.get('crashes', [])],
                curl_commands=data.get('curl_commands', []),
                message=f"Fuzzing complete: {data.get('total_crashes', 0)} crashes found"
            )

        elif result.state == 'FAILURE':
            return StatusResponse(
                task_id=task_id,
                status=TaskStatus.FAILED,
                progress_percent=0,
                total_tests_run=0,
                total_crashes=0,
                error=str(result.info),
                message="Fuzzing failed"
            )

        else:
            # Custom state updates from worker (RUNNING with progress)
            meta = result.info or {}
            return StatusResponse(
                task_id=task_id,
                status=TaskStatus.RUNNING,
                progress_percent=meta.get('progress_percent', 0),
                total_tests_run=meta.get('total_tests_run', 0),
                total_crashes=meta.get('total_crashes', 0),
                crashes=[CrashResult(**c) for c in meta.get('crashes', [])],
                curl_commands=meta.get('curl_commands', []),
                message="Fuzzing in progress..."
            )

    except Exception as e:
        logger.error(f"Error retrieving status: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve status")

@app.post("/validate-target")
def validate_target(url: str):
    try:
        response = requests.get(url, timeout=5)
        if response.status_code != 200:
            return {"status": "error", "message": "Target is not reachable"}
        return {"status": "ok"}
    except Exception:
        return {"status": "error", "message": "Could not connect to target"}

@app.post("/cancel/{task_id}")
async def cancel_job(task_id: str):
    """Cancel a fuzzing job."""
    try:
        result = AsyncResult(task_id, app=celery_app)
        result.revoke(terminate=True)

        return {
            "task_id": task_id,
            "status": "cancelled",
            "message": f"Job {task_id} cancelled"
        }
    except Exception as e:
        logger.error(f"Error cancelling job: {e}")
        raise HTTPException(status_code=500, detail="Failed to cancel job")

@app.get("/stats")
async def get_stats():
    """Get fuzzer statistics."""
    try:
        inspect = celery_app.control.inspect()
        active_tasks = inspect.active()
        registered_tasks = inspect.registered()

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "active_tasks": sum(len(tasks) for tasks in (active_tasks or {}).values()),
            "workers": len(active_tasks or {}),
            "registered_tasks": sum(len(tasks) for tasks in (registered_tasks or {}).values()),
        }
    except Exception as e:
        logger.error(f"Error retrieving stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve stats")

@app.on_event("startup")
async def startup_event():
    """Initialize on startup."""
    logger.info("Black-Box Fuzzer API starting up")
    try:
        redis_client.ping()
        logger.info("Redis connection successful")
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("Black-Box Fuzzer API shutting down")
    redis_client.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
