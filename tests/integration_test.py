import time
import subprocess
import requests
import sys
import os

def test_backend_startup():
    print("Starting backend...")
    # Start uvicorn in background
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--port", "8002"],
        cwd=os.getcwd(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    
    try:
        # Wait for startup
        print("Waiting for startup...")
        time.sleep(5)
        
        # Check if process is still running
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            print(f"Backend failed to start. Return code: {process.returncode}")
            print(f"STDOUT: {stdout.decode()}")
            print(f"STDERR: {stderr.decode()}")
            raise RuntimeError("Backend failed to start")

        # Query health endpoint
        print("Querying /health...")
        response = requests.get("http://localhost:8002/health")
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        print("✅ Backend is healthy")

    finally:
        print("Killing backend...")
        process.terminate()
        process.wait()

if __name__ == "__main__":
    try:
        test_backend_startup()
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
