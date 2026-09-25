from dataclasses import dataclass
from datetime import datetime


@dataclass
class Supplier:
    id: str
    name: str
    email: str
    country: str
    created_at: datetime
