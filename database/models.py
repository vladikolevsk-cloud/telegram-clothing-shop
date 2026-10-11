from dataclasses import dataclass

import aiosqlite


@dataclass(frozen=True, slots=True)
class Product:
    id: int
    name: str
    description: str | None
    price: float
    photo_id: str | None
    category: str

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "Product":
        return cls(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            price=row["price"],
            photo_id=row["photo_id"],
            category=row["category"],
        )


@dataclass(frozen=True, slots=True)
class ProductSize:
    size: str
    quantity: int
