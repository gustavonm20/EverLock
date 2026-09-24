import os

import uvicorn


def main() -> None:
    port = int(os.getenv("EVERLOCK_PORT", "8000"))
    if not 1 <= port <= 65535:
        raise ValueError("EVERLOCK_PORT deve estar entre 1 e 65535.")
    print(f"EverLock • simulador local: http://127.0.0.1:{port}", flush=True)
    uvicorn.run(
        "everlock.app:create_app", factory=True, host="127.0.0.1", port=port, access_log=False,
    )


if __name__ == "__main__":
    main()
