import math
import re


def squash_spaces(text: str) -> str:
    return " ".join(text.split())


def normalize_phone(raw: str) -> str | None:
    """Приводит украинский номер к виду +380XXXXXXXXX или возвращает None."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10 and digits.startswith("0"):
        digits = "38" + digits
    if len(digits) == 12 and digits.startswith("380"):
        return f"+{digits}"
    return None


def parse_price(raw: str) -> float | None:
    try:
        value = float(raw.replace(",", ".").replace(" ", ""))
    except ValueError:
        return None
    if not math.isfinite(value) or not 0 < value < 10_000_000:
        return None
    return value


def parse_size_stock(raw: str) -> dict[str, int] | None:
    """Parses stock entries formatted as 'S:3, M:2'."""
    raw = raw.strip()
    if raw.endswith("."):
        raw = raw[:-1].rstrip()

    sizes: dict[str, int] = {}
    for entry in raw.split(","):
        parts = entry.strip().rsplit(":", 1)
        if len(parts) != 2:
            return None
        size, raw_quantity = parts[0].strip().upper(), parts[1].strip()
        if not re.fullmatch(r"[\w./-]{1,20}", size, flags=re.UNICODE):
            return None
        if not raw_quantity.isdecimal():
            return None
        quantity = int(raw_quantity)
        if quantity < 1 or quantity > 100_000 or size in sizes:
            return None
        sizes[size] = quantity
    return sizes or None
