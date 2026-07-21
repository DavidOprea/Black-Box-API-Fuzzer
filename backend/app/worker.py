import subprocess
import re
from celery import Celery

celery_app = Celery("fuzzer_tasks", broker="redis://redis:6379/0", backend="redis://redis:6379/0")
NUM_WORKERS = 4
MAX_EXAMPLES = 100
MODE = "all"

@celery_app.task(bind=True)
def fuzz_api_task(self, target_openapi_url: str, header_name=None, header_value=None):
    # 1. Build the base command
    cmd = ["schemathesis", "run", target_openapi_url, 
           "--checks", "not_a_server_error", 
           "--workers" , f"{NUM_WORKERS}",
           "--max-examples", f"{MAX_EXAMPLES}", 
           "--mode", f"{MODE}",         
           "--no-color"]
    
    # 2. If the user provided an API key, inject it into the CLI command
    if header_name and header_value:
        cmd.extend(["-H", f"{header_name}: {header_value}"])
    
    # 3. Execute
    process = subprocess.Popen(cmd, 
                               stdout=subprocess.PIPE, 
                               stderr=subprocess.STDOUT, 
                               text=True,
                               bufsize=1)
    
    full_output = []
    tests_completed = 0

    for line in iter(process.stdout.readline, ''):
        full_output.append(line)

        # 2. Look for numbers followed by passed/failed/error/skipped 
        # Example match: [('5', 'passed'), ('3', 'failed')]
        stats = re.findall(r"(\d+)\s+(passed|failed|error|skipped)", line.lower())

        if stats:
            # Extract just the markers block and count its length
            line_total = sum(int(count) for count, status in stats)
            tests_completed += line_total
            
            # Broadcast to frontend
            self.update_state(
                state='PROGRESS',
                meta={
                    'total_tests_run': tests_completed,
                    'total_crashes': 0, 
                    'status': 'RUNNING',
                    'logs': "".join(full_output)
                }
            )
    
    process.stdout.close()
    process.wait()

    output_std = "".join(full_output)

    # Fallback just in case the fuzzer crashes entirely and prints no summary
    total_tests = tests_completed
    if total_tests == 0:
        total_tests = "Unknown (Crash)"

    # 4. Parse (Regex to find curl commands)
    raw_curl_blocks = re.findall(r"(curl -X .*?)(?=\n\n|\Z)", output_std, re.DOTALL)

    # 5. Clean the commands and extract metadata
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
        "total_tests": tests_completed, 
        "total_crashes": len(clean_curls),
        "crashes": crashes
    }