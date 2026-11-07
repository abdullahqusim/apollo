"""Runs Apollo: the FastAPI backend and built frontend on port 8000."""

import os
import sys
import subprocess
import uvicorn

if __name__ == "__main__":
    root_dir = os.path.abspath(os.path.dirname(__file__))
    backend_dir = os.path.join(root_dir, "backend")
    frontend_dist = os.path.join(root_dir, "frontend", "dist")

    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

    # Build frontend if dist is missing
    if not os.path.exists(frontend_dist):
        print("Building frontend...")
        subprocess.run(["npm", "run", "build"], cwd=os.path.join(root_dir, "frontend"), check=True, shell=True)

    print("Apollo")
    print("  Console:       http://localhost:8000")
    print("  Online sign-up: http://localhost:8000/join")
    print("  API docs:      http://localhost:8000/docs")

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False, workers=1)
