"""Pattern engine: records + teacher observations in, evidence-backed candidate patterns out.

Pure and deterministic. Every pattern carries its own evidence references, a strength classification
derived from counts, and caveats (gaps, excluded outliers, removed duplicates). Patterns are
candidates for teacher review, never labels and never conclusions.

Pattern kinds: strength | decline | conflict | anomaly | insufficient
(strength = sustained improvement; decline = sustained fall)
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from statistics import median
from typing import Any

from app.mcp_server.analysis import conflicts as cf
from app.mcp_server.analysis import outliers as ol
from app.mcp_server.analysis import sufficiency as sf
from app.mcp_server.analysis import trends as tr
from app.mcp_server.analysis.common import dedupe, humanise, missing_terms, pct, term_label, term_ord

ATTENDANCE_DIP = 8.0  # points below the learner's own median attendance to count as a dip
KIND_ORDER = {"decline": 0, "conflict": 1, "anomaly": 2, "strength": 3, "insufficient": 4}


# ---------- small builders ----------
def _pid(*parts: Any) -> str:
    return "PAT-" + hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:8].upper()


def _rec_ev(r: dict[str, Any], note: str | None = None) -> dict[str, Any]:
    p = r["pct"]
    default = f"{r['kind']}: {r.get('title')} = {p:.0f}%" if p is not None else f"{r['kind']}: {r.get('title')} (no score)"
    return {"type": "record", "id": r.get("id"), "term": r["term"], "note": note or default}


def _obs_ev(o: dict[str, Any], note: str) -> dict[str, Any]:
    return {"type": "observation", "id": o.get("id"), "term": o["term"], "note": note}


def _pattern(learner_id, kind, subtype, subject, skill, statement, strength, n_terms, n_records,
             channels, evidence, caveats, extra=None, key=()) -> dict[str, Any]:
    return {
        "pattern_id": _pid(learner_id, kind, subtype, subject, skill, *key),
        "learner_id": learner_id, "kind": kind, "subtype": subtype, "subject": subject, "skill": skill,
        "statement": statement, "evidence_strength": strength,
        "n_terms": n_terms, "n_records": n_records,
        "n_supporting_observations": sum(1 for e in evidence if e["type"] == "observation"),
        "channels": channels, "evidence": evidence, "caveats": caveats, "detail": extra or {},
    }


def _r1(x: float | None) -> float | None:
    return None if x is None else round(float(x), 1)


# ---------- main entry ----------
def analyse(learner_id: str, records: list[dict[str, Any]], observations: list[dict[str, Any]],
            subject: str | None = None) -> dict[str, Any]:
    mine = [r for r in records if r.get("learner_id", learner_id) == learner_id]
    cleaned, dropped = dedupe(mine)
    rows = [dict(r, pct=pct(r), ord=term_ord(r["term"])) for r in cleaned]
    obs = [dict(o, ord=term_ord(o["term"])) for o in observations if o.get("learner_id", learner_id) == learner_id]

    attendance = [r for r in rows if r["kind"] == "attendance"]
    work = [r for r in rows if r["kind"] != "attendance"]
    if subject:
        work = [r for r in work if r["subject"] == subject]
        obs = [o for o in obs if o.get("subject") in (subject, None)]

    att_pts = tr.term_means(attendance)
    att_trend = tr.trend(att_pts)
    att_values = [p["mean"] for p in att_pts]
    att_median = median(att_values) if att_values else None

    patterns: list[dict[str, Any]] = []
    checked: list[dict[str, Any]] = []
    trend_by_series: dict[tuple, dict[str, Any]] = {}

    groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for r in work:
        groups[(r["subject"], r.get("skill"))].append(r)

    for (subj, skill), grp in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1] or "")):
        scored = [r for r in grp if r["pct"] is not None]
        if not scored:
            continue

        # 1) screen out single anomalous scores (per assessment class), keep them for reporting
        flagged: list[dict[str, Any]] = []
        for cls in ("quiz", "coursework"):
            flagged += ol.detect_outliers([r for r in scored if ol.kind_class(r["kind"]) == cls])
        flagged_keys = {(f["ord"], f["kind"], f.get("title"), f["pct"]) for f in flagged}
        inliers = [r for r in scored if (r["ord"], r["kind"], r.get("title"), r["pct"]) not in flagged_keys]

        pts = tr.term_means(inliers)
        t = tr.trend(pts)
        n_terms, n_recs = len(pts), len(inliers)
        gaps = missing_terms([p["ord"] for p in pts])
        trend_by_series[(subj, skill)] = {**t, "gaps": gaps, "n_records": n_recs}

        result = "insufficient" if sf.classify(n_terms, n_recs, 1, []) == "none" else (
            {"up": "improving", "down": "declining"}.get(t["direction"], "no_significant_trend"))
        checked.append({
            "subject": subj, "skill": skill, "n_terms": n_terms, "n_records": n_recs,
            "slope_per_term": _r1(t["slope"]), "early_mean": _r1(t["early_mean"]), "late_mean": _r1(t["late_mean"]),
            "p_value": None if t["p_value"] is None else round(t["p_value"], 4), "result": result,
        })

        caveats: list[str] = []
        if gaps:
            caveats.append(f"No data for {', '.join(gaps)}; computed over the terms that have data only, nothing interpolated.")
        if flagged:
            caveats.append(f"{len(flagged)} outlying score(s) excluded from the trend and reported separately.")
        if dropped:
            caveats.append("Duplicate rows from repeated imports were counted once.")

        skill_obs = [o for o in obs if o.get("subject") == subj and o.get("skill") in (skill, None)]

        # 2) not enough data -> say so, do not guess
        if sf.classify(n_terms, n_recs, 1, []) == "none":
            patterns.append(_pattern(
                learner_id, "insufficient", "thin_series", subj, skill,
                f"Only {n_terms} term(s) and {n_recs} scored record(s) for {subj} {humanise(skill)}. "
                f"No pattern can be reported yet; needed: {'; '.join(sf.what_is_missing(n_terms, n_recs))}.",
                "none", n_terms, n_recs, ["scores"],
                [_rec_ev(r) for r in inliers] + [_obs_ev(o, f"{o.get('sentiment')} observation") for o in skill_obs],
                caveats, {"needs": sf.what_is_missing(n_terms, n_recs)}))
            continue

        # 3) sustained trend
        if t["direction"] in ("up", "down"):
            up = t["direction"] == "up"
            want = "strong" if up else "concern"
            support = [o for o in skill_obs if o.get("sentiment") == want]
            channels = ["scores"]
            evidence = [_rec_ev(r) for r in inliers]
            if support:
                channels.append("teacher_observations")
                evidence += [_obs_ev(o, f"{want} observation: {o['teacher_id']}") for o in support]
            att_down = (not up) and att_trend["direction"] == "down"
            if att_down:
                channels.append("attendance")
                evidence += [_rec_ev(a, f"attendance {a['pct']:.0f}%") for a in attendance if a["pct"] is not None]
            verb, word = ("rose", "improved") if up else ("fell", "declined")
            statement = (
                f"{subj} {humanise(skill)} {word} over {n_terms} terms: term averages {verb} from about "
                f"{t['early_mean']:.0f}% to about {t['late_mean']:.0f}% ({t['slope']:+.1f} points per term)."
            )
            patterns.append(_pattern(
                learner_id, "strength" if up else "decline", "improving" if up else "declining", subj, skill,
                statement, sf.classify(n_terms, n_recs, len(channels), gaps), n_terms, n_recs, channels,
                evidence, caveats,
                {"term_means": [{"term": p["term"], "mean": _r1(p["mean"]), "n": p["n"]} for p in pts],
                 "trend": {k: _r1(v) if isinstance(v, float) else v for k, v in t.items()}, "gaps": gaps}))

        # 4) kinds of evidence that disagree (timed quizzes vs coursework in the same skill)
        gap_info = cf.assessment_type_gap(inliers)
        if gap_info:
            pos = [o for o in skill_obs if o.get("sentiment") == "strong"]
            neg = [o for o in skill_obs if o.get("sentiment") == "concern"]
            channels = ["scores"] + (["teacher_observations"] if skill_obs else [])
            both = bool(pos and neg)
            statement = (
                f"{subj} {humanise(skill)}: quiz results average {gap_info['quiz_mean']:.0f}% while coursework "
                f"(assignments and projects) average {gap_info['coursework_mean']:.0f}%, a gap of "
                f"{abs(gap_info['gap']):.0f} points that holds in {gap_info['terms_consistent']} of "
                f"{gap_info['terms_shared']} terms with both."
                + (" Teacher observations for this skill point in both directions." if both else "")
                + " The data do not show why; this needs a teacher's interpretation."
            )
            evidence = [_rec_ev(r) for r in inliers] + [
                _obs_ev(o, f"{o.get('sentiment')} observation: {o['teacher_id']}") for o in skill_obs
                if o.get("sentiment") in ("strong", "concern")]
            patterns.append(_pattern(
                learner_id, "conflict", "assessment_type", subj, skill, statement,
                sf.classify(gap_info["terms_shared"], n_recs, len(channels), gaps),
                n_terms, n_recs, channels, evidence, caveats,
                {k: _r1(v) if isinstance(v, float) else v for k, v in gap_info.items()}))

        # 5) single anomalous scores: flag, attach context, never explain
        for f in flagged:
            ctx_obs = [o for o in obs if o["ord"] == f["ord"] and o.get("subject") in (subj, None)]
            att_ctx = [a for a in attendance if a["ord"] == f["ord"] and a["pct"] is not None
                       and att_median is not None and a["pct"] < att_median - ATTENDANCE_DIP]
            evidence = [_rec_ev(f, f"{f['kind']}: {f.get('title')} = {f['pct']:.0f}% (expected about {f['expected']:.0f}%)")]
            evidence += [_obs_ev(o, f"same-term observation ({o.get('sentiment')})") for o in ctx_obs]
            evidence += [_rec_ev(a, f"attendance {a['pct']:.0f}% against a usual {att_median:.0f}%") for a in att_ctx]
            below = f["residual"] < 0
            patterns.append(_pattern(
                learner_id, "anomaly", "single_score", subj, skill,
                f"{f.get('title')} scored {f['pct']:.0f}%, about {abs(f['residual']):.0f} points "
                f"{'below' if below else 'above'} this learner's usual level for {ol.kind_class(f['kind'])} results in "
                f"{subj} {humanise(skill)} (expected about {f['expected']:.0f}%). Excluded from the trend; "
                f"check same-term notes and documents for the conditions it was taken under.",
                "medium" if (ctx_obs or att_ctx) else "low", n_terms, n_recs, ["scores"]
                + (["teacher_observations"] if ctx_obs else []) + (["attendance"] if att_ctx else []),
                evidence, caveats,
                {"term": f["term"], "pct": _r1(f["pct"]), "expected": _r1(f["expected"]), "residual": _r1(f["residual"])},
                key=(f["term"], f.get("title"))))

    # 6) characterising language in teacher notes vs what the data show
    label_notes = [o for o in obs if cf.has_label_language(o.get("text", ""))]
    by_series: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for o in label_notes:
        by_series[(o.get("subject"), o.get("skill"))].append(o)
    for (subj, skill), notes in sorted(by_series.items(), key=lambda kv: (kv[0][0] or "", kv[0][1] or "")):
        series = trend_by_series.get((subj, skill))
        measured = "no series in the record"
        if series:
            d = series["direction"]
            measured = ({"up": f"the measured record rose from about {series['early_mean']:.0f}% to about {series['late_mean']:.0f}%",
                         "down": f"the measured record fell from about {series['early_mean']:.0f}% to about {series['late_mean']:.0f}%"}
                        .get(d, "the measured record shows no significant trend"))
        terms = sorted({o["term"] for o in notes})
        ev = [_obs_ev(o, "contains characterising language (a trait or ability label, not a described behaviour)") for o in notes]
        strength = "high" if (len(notes) >= 2 and series and series["direction"] != "none") else "medium"
        patterns.append(_pattern(
            learner_id, "conflict", "label_language", subj, skill,
            f"{len(notes)} teacher note(s) ({', '.join(terms)}) characterise the learner rather than describe "
            f"observed work; for {subj or 'this learner'} {humanise(skill)}, {measured}. "
            f"Treat the characterisations as unverified; report only evidenced behaviours.",
            strength, series["n_terms"] if series else 0, series["n_records"] if series else 0,
            ["teacher_observations"] + (["scores"] if series else []), ev, [],
            {"n_label_notes": len(notes), "terms": terms}))

    if not any(r["pct"] is not None for r in work):
        patterns.append(_pattern(
            learner_id, "insufficient", "no_scored_data", subject, None,
            "There are no scored records to analyse for this learner" + (f" in {subject}." if subject else "."),
            "none", 0, 0, [], [], [], {"needs": sf.what_is_missing(0, 0)}))

    patterns.sort(key=lambda p: (KIND_ORDER[p["kind"]], p["subject"] or "", p["skill"] or ""))

    all_ords = [r["ord"] for r in work if r["pct"] is not None]
    coursework = [r for r in work if r["kind"] in ("assignment", "project")]
    late = sum(1 for r in coursework if r.get("submitted_late"))
    data_quality = {
        "records_analysed": len(work),
        "duplicates_removed": len(dropped),
        "blank_scores": sum(1 for r in work if r["pct"] is None),
        "terms_with_data": sorted({term_label(o) for o in all_ords}),
        "terms_missing_within_span": missing_terms(sorted(set(all_ords))),
        "late_submissions": {"coursework_records": len(coursework), "late": late,
                             "rate": _r1(100 * late / len(coursework)) if coursework else None},
        "attendance": {"trend": att_trend["direction"],
                       "early": _r1(att_trend["early_mean"]), "late": _r1(att_trend["late_mean"])},
    }
    return {"learner_id": learner_id, "subject_filter": subject, "patterns": patterns,
            "checked": checked, "data_quality": data_quality}
