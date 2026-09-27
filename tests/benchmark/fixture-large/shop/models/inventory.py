from dataclasses import dataclass


@dataclass
class InventoryLevel:
    product_id: str
    on_hand: int
    reserved: int

    @property
    def available(self) -> int:
        return self.on_hand - self.reserved
