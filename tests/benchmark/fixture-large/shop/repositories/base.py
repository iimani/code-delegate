import sqlite3
from typing import Any, List, Optional, Sequence


class Repository:
    """Thin helper around a sqlite3 connection shared by all repositories."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def _one(self, sql: str, args: Sequence[Any] = ()) -> Optional[sqlite3.Row]:
        return self.conn.execute(sql, args).fetchone()

    def _all(self, sql: str, args: Sequence[Any] = ()) -> List[sqlite3.Row]:
        return self.conn.execute(sql, args).fetchall()

    def _exec(self, sql: str, args: Sequence[Any] = ()) -> int:
        cur = self.conn.execute(sql, args)
        self.conn.commit()
        return cur.rowcount
