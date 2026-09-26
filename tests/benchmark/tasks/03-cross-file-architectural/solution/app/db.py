class Database:
    def __init__(self, logger) -> None:
        self._logger = logger

    def connect(self) -> None:
        self._logger.info("[db] connecting to database")

    def query(self, sql: str) -> None:
        self._logger.info(f"[db] running query: {sql}")
