import subprocess
import re
from celery import Celery

celery_app = Celery("fuzzer_tasks", broker="redis://redis:6379/0", backend="redis://redis:6379/0")

@celery_app.task(bind=True)
def fuzz_api_task(self, target_openapi_url: str, header_name=None, header_value=None):
    # 1. Build the base command
    cmd = ["schemathesis", "run", target_openapi_url, "--checks", "not_a_server_error"]
    
    # 2. If the user provided an API key, inject it into the CLI command
    if header_name and header_value:
        cmd.extend(["-H", f"{header_name}: {header_value}"])
    
    # 3. Execute
    process = subprocess.run(cmd, capture_output=True, text=True)
    output = process.stdout + process.stderr

    # NEW: 4. Parse Total Tests dynamically from the summary line
    total_tests = 0
    # Look for the final summary line surrounded by equal signs
    summary_match = re.search(r"={3,}([^=]+)={3,}", output)
    
    if summary_match:
        summary_str = summary_match.group(1)
        # Find all numbers preceding standard test outcome keywords
        counts = re.findall(r"(\d+)\s+(?:passed|failed|errored|skipped|xfailed|xpassed)", summary_str)
        # Sum them all up to get the true total
        total_tests = sum(int(c) for c in counts)
        
    # Fallback just in case the fuzzer crashes entirely and prints no summary
    if total_tests == 0:
        total_tests = "Unknown (Crash)"
    
    # 5. Parse (Regex to find curl commands)
    raw_curl_blocks = re.findall(r"(curl -X .*?)(?=\n\n|\Z)", output, re.DOTALL)

    # 6. Clean the commands and extract metadata
    crashes = []
    clean_curls = []

    for curl in raw_curl_blocks:
        # Slice off the "st replay <id>" suffix
        clean_curl = re.sub(r"\s+st replay \w+", "", curl).strip()
        clean_curls.append(clean_curl)
        
        # Extract the HTTP Method (e.g., GET, POST, PUT)
        method_match = re.search(r"curl -X ([A-Z]+)", clean_curl)
        method = method_match.group(1) if method_match else "UNKNOWN"
        
        # Extract the URL Path (everything after the domain name)
        url_match = re.search(r"https?://[^/\s]+(/\S*)", clean_curl)
        path = url_match.group(1) if url_match else "unknown"
        path = path.rstrip("'\"") # Clean up any trailing quotes
        
        # Append the dynamically parsed data
        crashes.append({
            "method": method,
            "path": path,
            "status_code": 500, # not_a_server_error check strictly catches 500s
            "curl_command": clean_curl
        })
    
    return {
        "total_tests": 100, 
        "total_crashes": len(clean_curls),
        "crashes": crashes
    }