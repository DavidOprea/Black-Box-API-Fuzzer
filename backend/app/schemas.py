from pydantic import BaseModel, HttpUrl, validator
from typing import Optional, List
from enum import Enum

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"

class FuzzRequest(BaseModel):
    target_openapi_url: HttpUrl
    api_key_header: Optional[str] = None
    api_key_value: Optional[str] = None
    consent_acknowledged: bool

    @validator('consent_acknowledged')
    def validate_consent(cls, v):
        if not v:
            raise ValueError("You must acknowledge that you own this API")
        return v

class FuzzResponse(BaseModel):
    task_id: str
    status: TaskStatus
    message: str

class CrashResult(BaseModel):
    method: str
    path: str
    status_code: int
    payload: Optional[str] = None
    curl_command: Optional[str] = None

class StatusResponse(BaseModel):
    task_id: str
    status: TaskStatus
    progress_percent: int
    total_tests_run: int
    total_crashes: int
    crashes: List[CrashResult] = []
    curl_commands: List[str] = []
    message: str = ""
    error: Optional[str] = None

class FuzzerConfig(BaseModel):
    concurrency_limit: int = 20
    rate_limit_rps: float = 10.0
    timeout_seconds: int = 300
    max_failures: int = 100
