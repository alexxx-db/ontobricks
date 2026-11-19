import copy

import uvicorn
from uvicorn.config import LOGGING_CONFIG

from backend.runtime import config
from backend.runtime.app import create_app

# uvicorn's own config, with its error log moved from stderr to stdout.
LOG_CONFIG = copy.deepcopy(LOGGING_CONFIG)
LOG_CONFIG["handlers"]["default"]["stream"] = "ext://sys.stdout"


def main() -> None:
    settings = config.load()
    uvicorn.run(
        create_app(settings),
        host="0.0.0.0",
        port=settings.port,
        log_config=LOG_CONFIG,
        timeout_graceful_shutdown=10,
    )


if __name__ == "__main__":
    main()
