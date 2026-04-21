import os

import uvicorn
from wispr_local.server import app

if __name__ == "__main__":
    port = int(os.environ.get("WISPR_PORT", "8001"))
    print(f"Port: {port}")
    print(f"Starting Wispr Local Backend on http://127.0.0.1:{port} ...")
    uvicorn.run(app, host="127.0.0.1", port=port)