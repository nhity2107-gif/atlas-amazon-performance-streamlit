from __future__ import annotations

import pandas as pd


# Confirmed source-data corrections. Keep these explicit until TOTAL ASIN is fixed.
FBA_ASIN_OVERRIDES = frozenset({"B0F1XZT333", "B0F1XPZ1JX"})


def apply_fulfillment_overrides(
    frame: pd.DataFrame,
    asin_column: str = "asin",
    fulfillment_column: str = "fulfill_by",
) -> pd.DataFrame:
    """Return a copy with confirmed ASIN-level fulfillment corrections applied."""
    corrected = frame.copy()
    if asin_column not in corrected or fulfillment_column not in corrected:
        return corrected
    normalized_asins = (
        corrected[asin_column].fillna("").astype(str).str.strip().str.upper()
    )
    corrected.loc[normalized_asins.isin(FBA_ASIN_OVERRIDES), fulfillment_column] = "FBA"
    return corrected
