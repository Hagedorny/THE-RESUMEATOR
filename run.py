#!/usr/bin/env python3
"""
Resume Tailoring Agent v2
Run: python run.py
Then open http://localhost:8000
"""

import yaml
import uvicorn
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.yaml"

def main():
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    server = config.get("server", {})
    host = server.get("host", "127.0.0.1")
    port = server.get("port", 8000)

    print(f"""
    Resume Tailoring Agent v2
    http://{host}:{port}
    Press Ctrl+C to stop
    """)

    uvicorn.run("backend.app:app", host=host, port=port, reload=True)

if __name__ == "__main__":
    main()
