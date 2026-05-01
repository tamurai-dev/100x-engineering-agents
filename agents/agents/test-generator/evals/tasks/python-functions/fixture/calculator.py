"""計算ユーティリティ関数群"""

from __future__ import annotations


def add(a: float, b: float) -> float:
    return a + b


def divide(a: float, b: float) -> float:
    if b == 0:
        raise ZeroDivisionError("Division by zero is not allowed")
    return a / b


def mean(values: list[float]) -> float:
    if not values:
        raise ValueError("Cannot compute mean of empty list")
    return sum(values) / len(values)


def compound_interest(
    principal: float,
    annual_rate: float,
    years: int,
    compounds_per_year: int = 12,
) -> float:
    if principal < 0:
        raise ValueError("Principal must be non-negative")
    if annual_rate < 0:
        raise ValueError("Annual rate must be non-negative")
    if years < 0:
        raise ValueError("Years must be non-negative")
    if compounds_per_year <= 0:
        raise ValueError("Compounds per year must be positive")

    rate_per_period = annual_rate / compounds_per_year
    total_periods = compounds_per_year * years
    return principal * (1 + rate_per_period) ** total_periods
