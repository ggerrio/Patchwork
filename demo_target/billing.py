"""Simple billing module with intentional bugs for Patchwork E2E demonstration."""


def calculate_unit_price(total_amount: float, quantity: int) -> float:
    """Compute unit price for a line item."""
    # Bug 1: ZeroDivisionError when quantity == 0
    return total_amount / quantity


def format_invoice(payload: dict[str, object]) -> str:
    """Format an invoice summary string."""
    # Bug 2: KeyError when 'currency' is omitted
    return f"Invoice #{payload['id']}: {payload['amount']} {payload['currency']}"


def apply_discount(prices: list[float], discount_pct: float | None) -> float:
    """Return total after applying an optional percentage discount."""
    # Bug 3: TypeError when discount_pct is None
    subtotal = sum(prices)
    return round(subtotal * (1.0 - discount_pct / 100.0), 2)

