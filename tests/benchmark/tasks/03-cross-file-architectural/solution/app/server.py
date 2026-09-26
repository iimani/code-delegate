class Server:
    def __init__(self, logger) -> None:
        self._logger = logger

    def start(self) -> None:
        self._logger.info("[server] listening on port 8080")

    def handle_request(self, path: str) -> None:
        self._logger.info(f"[server] handling request: {path}")
