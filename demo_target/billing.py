"""Simple billing module with intentional bugs for Patchwork E2E demonstration."""


def calculate_unit_price(total_amount: float, quantity: int) -> float:
    """Compute unit price for a line item."""
    if quantity == 0:
        return 0.0
    return total_amount / quantity


def format_invoice(payload: dict[str, object]) -> str:
    """Format an invoice summary string."""
    currency = payload.get('currency', 'USD')
    return f"Invoice #{payload['id']}: {payload['amount']} {currency}"


def apply_discount(prices: list[float], discount_pct: float | None) -> float:
    """Return total after applying an optional percentage discount."""
    subtotal = sum(prices)
    if discount_pct is None:
        return float(subtotal)
    return round(subtotal * (1.0 - discount_pct / 100.0), 2)
