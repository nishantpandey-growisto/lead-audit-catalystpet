#!/usr/bin/env python3
"""Fetch PageSpeed Insights data for all URLs and write pagespeed.json"""
import json
import urllib.request
import urllib.parse
import sys
import os

KEY = os.environ.get("PAGESPEED_API_KEY", "")

URLS = {
    "client": "https://catalystpet.com",
    "competitors": [
        {"name": "Pretty Litter", "url": "https://prettylitter.com", "blocked": True, "block_reason": "Site returns 403 to PageSpeed Insights crawler (Netlify WAF block)"},
        {"name": "Tuft + Paw", "url": "https://tuftandpaw.com"},
        {"name": "Open Farm", "url": "https://openfarmpet.com"},
        {"name": "Petco", "url": "https://www.petco.com/shop/en/petcostore", "lab_blocked": True, "block_reason": "Lighthouse lab test blocked (403); CrUX field data available"},
        {"name": "PetSmart", "url": "https://www.petsmart.com"},
    ]
}


def fetch_psi(url, strategy):
    api_url = (
        f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
        f"?url={urllib.parse.quote(url, safe='')}"
        f"&strategy={strategy}&category=performance&key={KEY}"
    )
    print(f"  Fetching {strategy}: {url}", file=sys.stderr)
    try:
        req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  ERROR fetching {url} [{strategy}]: {e}", file=sys.stderr)
        return None


def extract_metrics(data):
    if not data:
        return None
    lh = data.get("lighthouseResult", {})
    score_raw = lh.get("categories", {}).get("performance", {}).get("score")
    score = round(score_raw * 100) if score_raw is not None else None
    audits = lh.get("audits", {})

    def get_audit(key):
        a = audits.get(key, {})
        return a.get("numericValue"), a.get("displayValue")

    fcp_n, fcp_d = get_audit("first-contentful-paint")
    lcp_n, lcp_d = get_audit("largest-contentful-paint")
    tbt_n, tbt_d = get_audit("total-blocking-time")
    cls_n, cls_d = get_audit("cumulative-layout-shift")
    si_n, si_d = get_audit("speed-index")

    # Score class
    if score is None:
        score_class = "poor"
    elif score >= 90:
        score_class = "good"
    elif score >= 50:
        score_class = "moderate"
    else:
        score_class = "poor"

    # CWV statuses
    def lcp_status(ms):
        if ms is None: return "unknown"
        if ms <= 2500: return "pass"
        if ms <= 4000: return "needs-improvement"
        return "fail"

    def fcp_status(ms):
        if ms is None: return "unknown"
        if ms <= 1800: return "pass"
        if ms <= 3000: return "needs-improvement"
        return "fail"

    def tbt_status(ms):
        if ms is None: return "unknown"
        if ms <= 200: return "pass"
        if ms <= 600: return "needs-improvement"
        return "fail"

    def cls_status(val):
        if val is None: return "unknown"
        if val <= 0.1: return "pass"
        if val <= 0.25: return "needs-improvement"
        return "fail"

    def status_class(s):
        return s  # pass/needs-improvement/fail/unknown map directly

    lcp_s = lcp_status(lcp_n)
    fcp_s = fcp_status(fcp_n)
    tbt_s = tbt_status(tbt_n)
    cls_s = cls_status(cls_n)

    return {
        "score": score,
        "score_class": f"score-cell-{score_class}",
        "fcp": fcp_d or "N/A",
        "fcp_ms": round(fcp_n) if fcp_n else None,
        "fcp_class": f"cwv-{fcp_s}",
        "fcp_status": fcp_s,
        "lcp": lcp_d or "N/A",
        "lcp_ms": round(lcp_n) if lcp_n else None,
        "lcp_class": f"cwv-{lcp_s}",
        "lcp_status": lcp_s,
        "tbt": tbt_d or "N/A",
        "tbt_ms": round(tbt_n) if tbt_n else None,
        "tbt_class": f"cwv-{tbt_s}",
        "tbt_status": tbt_s,
        "cls": cls_d or "N/A",
        "cls_raw": round(cls_n, 4) if cls_n is not None else None,
        "cls_class": f"cwv-{cls_s}",
        "cls_status": cls_s,
        "si": si_d or "N/A",
        "si_ms": round(si_n) if si_n else None,
        "inp": None,
    }


def extract_crux(data):
    if not data:
        return None
    le = data.get("loadingExperience", {})
    if not le:
        return None
    metrics = le.get("metrics", {})
    if not metrics:
        return None
    result = {
        "overall": le.get("overall_category"),
        "fcp_ms": None, "fcp_category": None,
        "lcp_ms": None, "lcp_category": None,
        "cls_score": None, "cls_category": None,
        "inp_ms": None, "inp_category": None,
        "ttfb_ms": None, "ttfb_category": None,
    }
    for k, v in metrics.items():
        p = v.get("percentile")
        cat = v.get("category")
        if k == "FIRST_CONTENTFUL_PAINT_MS":
            result["fcp_ms"] = p; result["fcp_category"] = cat
        elif k == "LARGEST_CONTENTFUL_PAINT_MS":
            result["lcp_ms"] = p; result["lcp_category"] = cat
        elif k == "CUMULATIVE_LAYOUT_SHIFT_SCORE":
            result["cls_score"] = p; result["cls_category"] = cat
        elif k == "INTERACTION_TO_NEXT_PAINT":
            result["inp_ms"] = p; result["inp_category"] = cat
        elif k == "EXPERIMENTAL_TIME_TO_FIRST_BYTE":
            result["ttfb_ms"] = p; result["ttfb_category"] = cat
    return result


def build_table_row(name, url, mobile, is_client=False, blocked=False):
    row_class = "client-row" if is_client else "competitor-row"
    if blocked:
        sc = "score-cell-poor"
        score = "Blocked"
    elif mobile is None:
        sc = "score-cell-poor"
        score = "N/A"
    else:
        sc = mobile.get("score_class", "score-cell-poor")
        raw_score = mobile.get("score")
        score = str(raw_score) if raw_score is not None else "N/A"
    lcp = mobile.get("lcp", "N/A") if mobile else "N/A"
    fcp = mobile.get("fcp", "N/A") if mobile else "N/A"
    tbt = mobile.get("tbt", "N/A") if mobile else "N/A"
    cls = mobile.get("cls", "N/A") if mobile else "N/A"

    lcp_s = mobile.get("lcp_status", "unknown") if mobile else "unknown"
    fcp_s = mobile.get("fcp_status", "unknown") if mobile else "unknown"
    tbt_s = mobile.get("tbt_status", "unknown") if mobile else "unknown"
    cls_s = mobile.get("cls_status", "unknown") if mobile else "unknown"

    def badge(s):
        if s == "pass": return '<span class="badge-pass">PASS</span>'
        if s == "needs-improvement": return '<span class="badge-ni">NI</span>'
        if s == "fail": return '<span class="badge-fail">FAIL</span>'
        return '<span class="badge-unknown">N/A</span>'

    return (
        f'<tr class="{row_class}">'
        f'<td class="site-name">{name}</td>'
        f'<td class="{sc}">{score}</td>'
        f'<td>{lcp} {badge(lcp_s)}</td>'
        f'<td>{fcp} {badge(fcp_s)}</td>'
        f'<td>{tbt} {badge(tbt_s)}</td>'
        f'<td>{cls} {badge(cls_s)}</td>'
        f'</tr>'
    )


def cwv_summary(mobile):
    if not mobile:
        return {"pass_count": 0, "total": 4, "class": "cwv-poor", "icon": "x"}
    statuses = [
        mobile.get("lcp_status"),
        mobile.get("fcp_status"),
        mobile.get("tbt_status"),
        mobile.get("cls_status"),
    ]
    pass_count = sum(1 for s in statuses if s == "pass")
    if pass_count >= 3:
        cls = "cwv-good"
        icon = "check"
    elif pass_count >= 2:
        cls = "cwv-moderate"
        icon = "warning"
    else:
        cls = "cwv-poor"
        icon = "x"
    return {"pass_count": pass_count, "total": 4, "class": cls, "icon": icon}


def build_verdict(client_mobile):
    if not client_mobile:
        return "Unable to fetch performance data.", ""
    score = client_mobile.get("score", 0)
    lcp_s = client_mobile.get("lcp_status")
    fcp_s = client_mobile.get("fcp_status")
    tbt_s = client_mobile.get("tbt_status")

    if score >= 70:
        verdict = "Good mobile performance"
    elif score >= 50:
        verdict = "Moderate mobile performance — improvement needed"
    else:
        verdict = "Poor mobile performance — significant issues"

    issues = []
    if lcp_s in ("needs-improvement", "fail"):
        lcp = client_mobile.get("lcp", "")
        issues.append(f"LCP at {lcp} (target: ≤2.5s)")
    if fcp_s in ("needs-improvement", "fail"):
        fcp = client_mobile.get("fcp", "")
        issues.append(f"FCP at {fcp} (target: ≤1.8s)")
    if tbt_s in ("needs-improvement", "fail"):
        tbt = client_mobile.get("tbt", "")
        issues.append(f"TBT at {tbt} (target: ≤200ms)")

    if issues:
        narrative = f"Catalyst Pet scores {score}/100 on mobile. Primary issues: {'; '.join(issues)}."
    else:
        narrative = f"Catalyst Pet scores {score}/100 on mobile with good Core Web Vitals."
    return verdict, narrative


# ── Main ─────────────────────────────────────────────────────────────────────

print("Fetching client data...", file=sys.stderr)
client_mobile_raw = fetch_psi(URLS["client"], "mobile")
client_desktop_raw = fetch_psi(URLS["client"], "desktop")

client_mobile = extract_metrics(client_mobile_raw)
client_desktop = extract_metrics(client_desktop_raw)
client_crux = extract_crux(client_mobile_raw)

competitors_out = []
table_rows = []

# Client row first
table_rows.append(build_table_row("Catalyst Pet (Client)", URLS["client"], client_mobile, is_client=True))

for comp in URLS["competitors"]:
    print("Fetching competitor: " + comp["name"] + "...", file=sys.stderr)
    is_blocked = comp.get("blocked", False)
    is_lab_blocked = comp.get("lab_blocked", False)

    if is_blocked:
        # Site blocks PSI entirely — skip API call
        mob_raw = None
        desk_raw = None
    else:
        mob_raw = fetch_psi(comp["url"], "mobile")
        desk_raw = fetch_psi(comp["url"], "desktop")

    mob = extract_metrics(mob_raw)
    desk = extract_metrics(desk_raw)
    crux = extract_crux(mob_raw)

    comp_entry = {
        "name": comp["name"],
        "url": comp["url"],
        "mobile": mob,
        "desktop": desk,
        "crux": crux,
    }
    if is_blocked or is_lab_blocked:
        comp_entry["fetch_note"] = comp.get("block_reason", "Data unavailable")

    competitors_out.append(comp_entry)
    table_rows.append(build_table_row(comp["name"], comp["url"], mob, blocked=is_blocked))

table_html = "\n".join(table_rows)
verdict, narrative = build_verdict(client_mobile)

output = {
    "client": {
        "url": URLS["client"],
        "mobile": client_mobile,
        "desktop": client_desktop,
        "crux": client_crux,
    },
    "competitors": competitors_out,
    "competition_table_html": table_html,
    "cwv_summary": cwv_summary(client_mobile),
    "verdict": verdict,
    "narrative": narrative,
}

out_path = "/Users/growisto/Documents/Claude_Code/_audit_reports/catalystpet-lead/data/pagespeed.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2)

print(f"Written to {out_path}", file=sys.stderr)
print(json.dumps(output, indent=2))
