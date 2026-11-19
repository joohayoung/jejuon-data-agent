"""순위·분위 (순수 코드). 값이 있는 행정동만 비교 대상으로 삼는다."""
from __future__ import annotations

import pandas as pd


def rank(values: pd.Series, direction: str) -> pd.DataFrame:
    """direction: high_good/none → 큰 값이 1위, low_good → 작은 값이 1위. 동점은 같은 순위(min)."""
    v = values.dropna()
    ascending = direction == "low_good"
    r = v.rank(method="min", ascending=ascending).astype(int)
    return pd.DataFrame({"value": v, "rank": r, "n": len(v)})


def quartile_label(r: int, n: int, q: float, direction: str) -> str:
    """상위 q 안 / 하위 q 안 / 그 밖. 순위 r은 1이 '좋은 쪽'(방향 없음이면 큰 쪽)."""
    if r <= n * q:
        top = True
    elif r > n * (1 - q):
        top = False
    else:
        return "보통"
    if direction == "none":
        return "높음" if top else "낮음"
    return "유리" if top else "불리"
