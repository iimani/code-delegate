from typing import Optional, Protocol

from app.db import Database
from app.server import Server


class Logger(Protocol):
    def info(self, message: str) -> None: ...


class ConsoleLogger:
    def info(self, message: str) -> None:
        print(message)


class Container:
    def __init__(self, logger: Logger) -> None:
        self.logger = logger
        self.db = Database(logger)
        self.server = Server(logger)


def build_container(logger: Optional[Logger] = None) -> Container:
    return Container(logger if logger is not None else ConsoleLogger())
