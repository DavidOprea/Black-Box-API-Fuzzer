export enum TaskStatus {
  PENDING = "pending",
  RUNNING = "running",
  SUCCESS = "success",
  FAILED = "failed",
}

export interface CrashResult {
  method: string;
  path: string;
  status_code: number;
  payload: Record<string, any>;
  curl_command: string;
}

export interface StatusResponse {
  task_id: string;
  status: TaskStatus;
  progress_percent: number;
  total_tests_run: number;
  total_crashes: number;
  crashes: CrashResult[];
  curl_commands: string[];
  message: string;
  logs?: string;
  error?: string;
}

export interface FuzzRequest {
  target_openapi_url: string;
  api_key_header?: string;
  api_key_value?: string;
  consent_acknowledged: boolean;
}

export interface FuzzResponse {
  task_id: string;
  status: TaskStatus;
  message: string;
}
