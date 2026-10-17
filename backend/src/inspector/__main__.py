"""Single-worker ASGI entry point; HTTPS is terminated by the trusted local proxy."""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "inspector.app:create_app",
        factory=True,
        workers=1,
        host="0.0.0.0",
        port=8000,
        proxy_headers=False,
        access_log=False,
        ws="websockets",
        ws_max_size=16_384,
        ws_max_queue=16,
    )
