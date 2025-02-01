import uvicorn
import os

if __name__ == "__main__":
    log_level = os.getenv("LOG_LEVEL", "info")
    reload = os.getenv("RELOAD", "false").lower() == "true"

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=reload,
        log_level=log_level,
        access_log=True
    ) 