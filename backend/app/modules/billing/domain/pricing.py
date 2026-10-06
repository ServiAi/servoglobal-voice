from decimal import Decimal


def savings(minutes: Decimal, provider_price: Decimal | None, serviglobal_price: Decimal):
    serviglobal_cost = minutes * serviglobal_price
    if provider_price is None:
        return None, serviglobal_cost, None, None
    provider_cost = provider_price * minutes
    amount = provider_cost - serviglobal_cost
    percent = amount / provider_cost * Decimal("100") if provider_cost > 0 else None
    return provider_cost, serviglobal_cost, amount, percent
