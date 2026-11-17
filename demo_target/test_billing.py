"""Pytest suite for demo_target/billing.py."""

try:
    from demo_target.billing import apply_discount, calculate_unit_price, format_invoice
except ImportError:
    from billing import apply_discount, calculate_unit_price, format_invoice


def test_calculate_unit_price_zero_quantity() -> None:
    assert calculate_unit_price(100.0, 4) == 25.0
    assert calculate_unit_price(100.0, 0) == 0.0


def test_format_invoice_default_currency() -> None:
    assert format_invoice({"id": 42, "amount": 99.5}) == "Invoice #42: 99.5 USD"


def test_apply_discount_none() -> None:
    assert apply_discount([50.0, 50.0], 10.0) == 90.0
    assert apply_discount([50.0, 50.0], None) == 100.0
