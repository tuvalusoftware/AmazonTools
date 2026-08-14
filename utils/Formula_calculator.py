"""
Shared formula library for BSR-derived metrics.

All business-logic calculations that translate BSR rank, price, and royalty
rate into estimated sales/profit figures live here so that every consumer
(email digest, PDF report, tests) uses the same numbers.

Convention
----------
``profit_pct`` is **always** passed as the raw DB value (e.g. ``70.0``).
Methods in this module divide by 100 internally — callers must NOT pre-divide.
"""

from __future__ import annotations


class Formula:
    """Stateless BSR metric formulas."""

    # Power-law constant tuned to Amazon Kindle BSR empirical data.
    _BSR_COEFFICIENT: float = 10_000.0
    _BSR_EXPONENT: float = 0.70

    @staticmethod
    def estimated_units_per_day(rank: int) -> int:
        """Estimate daily unit sales from a BSR *rank*.

        Uses the heuristic power-law:  ``max(1, round(10_000 / rank^0.70))``.

        Parameters
        ----------
        rank:
            Best-Seller Rank (positive integer; lower = more popular).

        Returns
        -------
        int
            Estimated units sold per day (minimum 1).
        """
        if rank <= 0:
            return 1
        return max(1, round(Formula._BSR_COEFFICIENT / rank ** Formula._BSR_EXPONENT))

    @staticmethod
    def daily_profit(rank: int, price: float, profit_pct: float) -> float:
        """Estimate daily author profit.

        Parameters
        ----------
        rank:
            BSR rank (positive integer).
        price:
            Book sale price in USD.
        profit_pct:
            Royalty rate as stored in the DB — e.g. ``70.0`` for 70 %.
            This method divides by 100 internally.

        Returns
        -------
        float
            ``estimated_units_per_day(rank) * price * (profit_pct / 100)``.
        """
        units = Formula.estimated_units_per_day(rank)
        return units * price * (profit_pct / 100.0)

    @staticmethod
    def daily_profit_per_unit(price: float, profit_pct: float) -> float:
        """Royalty earned per unit sold (price × royalty rate).

        Parameters
        ----------
        price:
            Book sale price in USD.
        profit_pct:
            Royalty rate as stored in the DB — e.g. ``70.0`` for 70 %.

        Returns
        -------
        float
            ``price * (profit_pct / 100)``.
        """
        return price * (profit_pct / 100.0)
