"""Decide whether there is enough evidence to say anything, and how strong it is.

Evidence strength is a statement about the DATA (how many terms, records and independent kinds of
evidence back a pattern). It is never a score for the learner.
"""
from __future__ import annotations

MIN_TERMS = 4      # terms with scored data before a trend or conflict can be claimed
MIN_RECORDS = 8    # scored records behind the claim
HIGH_TERMS = 6
HIGH_RECORDS = 15


def classify(n_terms: int, n_records: int, n_channels: int, gaps: list[str]) -> str:
    """'none' | 'medium' | 'high'.

    high   : >= 6 terms, >= 15 records, >= 2 independent channels (scores, teacher
             observations, attendance) and no missing terms inside the span
    medium : enough to report, but short, single-channel, or with a gap in the record
    none   : below the minimum; the correct output is 'insufficient data'
    """
    if n_terms < MIN_TERMS or n_records < MIN_RECORDS:
        return "none"
    if n_terms >= HIGH_TERMS and n_records >= HIGH_RECORDS and n_channels >= 2 and not gaps:
        return "high"
    return "medium"


def what_is_missing(n_terms: int, n_records: int) -> list[str]:
    out = []
    if n_terms < MIN_TERMS:
        out.append(f"scored data from at least {MIN_TERMS} terms (have {n_terms})")
    if n_records < MIN_RECORDS:
        out.append(f"at least {MIN_RECORDS} scored records (have {n_records})")
    return out
