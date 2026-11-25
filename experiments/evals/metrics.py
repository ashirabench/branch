"""pass@k and pass^k from n trials of which c passed (Anthropic's guide; Chen et al. 2021 for pass@k).

pass@k   the chance that at least one of k trials passes: right when one good attempt is enough.
pass^k   the chance that all k trials pass: right for an agent a person relies on every time.
Both are the unbiased estimates from n >= k trials, drawing k of them without replacement.
"""
from math import comb


def pass_at_k(n, c, k):
    return 1.0 - comb(n - c, k) / comb(n, k) if n >= k else float("nan")


def pass_hat_k(n, c, k):
    return comb(c, k) / comb(n, k) if n >= k else float("nan")
