#!/usr/bin/env python3
"""
Lead Audit Build Script — Auto-reads from data/*.json
======================================================
This script reads structured JSON data files produced by parallel agents
and generates the final index.html from the template.

Usage:
  1. Agents write data files to _audit_reports/{brand}-lead/data/
  2. Run: python3 build.py
  3. Open index.html to preview

Data files required (see data_schemas.md for full schemas):
  - data/config.json         (Phase 0: brand info, competitors, industry)
  - data/pagespeed.json      (Phase 1: PSI scores for client + competitors)
  - data/traffic.json        (Phase 1: SimilarWeb + proxy signals)
  - data/benchmark_context.json (Phase 1: industry benchmarks)
  - data/ux_findings.json    (Phase 2: all findings + screenshot paths)
  - data/tech_stack.json     (Phase 2: platform, theme, checkout, payments)
  - data/app_ecosystem.json  (Phase 2: detected apps, missing categories)

Backward compatible: If data/ folder doesn't exist, falls back to manual mode
with empty TODO placeholders (legacy behavior).
"""

import re, os, sys, json
from datetime import datetime

# ══════════════════════════════════════════════════════════════
# PATHS
# ══════════════════════════════════════════════════════════════

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
TEMPLATE = os.path.join(PROJECT_ROOT, "_cro_audit_system", "templates", "lead_audit_spa_template.html")
OUTPUT = os.path.join(SCRIPT_DIR, "index.html")


# ══════════════════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════════════════

def load_json(filename):
    """Load a JSON file from the data/ directory. Returns None if not found."""
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return json.load(f)


def check_data_files():
    """Check which data files exist and report status."""
    required = ["config.json", "pagespeed.json", "traffic.json",
                "benchmark_context.json", "ux_findings.json",
                "tech_stack.json", "app_ecosystem.json"]
    found = []
    missing = []
    for f in required:
        if os.path.exists(os.path.join(DATA_DIR, f)):
            found.append(f)
        else:
            missing.append(f)
    return found, missing


# ══════════════════════════════════════════════════════════════
# FINDING CARD HTML GENERATOR
# ══════════════════════════════════════════════════════════════

def card(header, client_img, client_label, bench_img, bench_label, observations, recommendations, benchmark_tag):
    """Generate a finding card HTML block from structured data."""
    obs_li = "\n".join(f"                                                    <li>{o}</li>" for o in observations)
    rec_li = "\n".join(f"                                                    <li>{r}</li>" for r in recommendations)

    if client_img is None:
        client_html = f'''<div class="finding-screenshot-missing">
                                                    <div class="missing-icon">✗</div>
                                                    <div class="missing-text">Feature not present</div>
                                                </div>
                                                <div class="finding-screenshot-label client-label">{client_label}</div>'''
    else:
        client_html = f'''<img src="{client_img}" alt="{client_label}">
                                                <div class="finding-screenshot-label client-label">{client_label}</div>'''

    if bench_img is None:
        bench_html = f'''<div class="finding-screenshot-missing" style="border-color:#10b981;">
                                                    <div class="missing-icon" style="color:#6b7280;">—</div>
                                                    <div class="missing-text" style="color:#6b7280;">No benchmark needed</div>
                                                </div>
                                                <div class="finding-screenshot-label benchmark-label">{bench_label or "Anti-pattern — avoid this"}</div>'''
    else:
        bench_html = f'''<img src="{bench_img}" alt="{bench_label}">
                                                <div class="finding-screenshot-label benchmark-label">{bench_label}</div>'''

    return f"""<div class="finding-card">
                                    <div class="finding-card-header">
                                        {header}
                                    </div>
                                    <div class="finding-card-body">
                                        <div class="finding-screenshots">
                                            <div class="finding-screenshot">
                                                {client_html}
                                            </div>
                                            <div class="finding-screenshot">
                                                {bench_html}
                                            </div>
                                        </div>
                                        <div class="finding-analysis">
                                            <div class="finding-observations">
                                                <span class="finding-section-header observations-header">Observations</span>
                                                <ul>
{obs_li}
                                                </ul>
                                            </div>
                                            <div class="finding-recommendations">
                                                <span class="finding-section-header recommendations-header">Recommendations</span>
                                                <ul>
{rec_li}
                                                </ul>
                                                <span class="finding-benchmark-tag">{benchmark_tag}</span>
                                            </div>
                                        </div>
                                    </div>
                                </div>"""


def build_finding_cards(findings_list):
    """Build HTML for a list of finding objects from ux_findings.json."""
    cards = []
    for f in findings_list:
        cards.append(card(
            f["header"],
            f.get("client_screenshot"),  # None → placeholder
            f.get("client_label", ""),
            f.get("benchmark_screenshot", ""),
            f.get("benchmark_label", ""),
            f.get("observations", []),
            f.get("recommendations", []),
            f.get("benchmark_tag", ""),
        ))
    return "\n\n".join(cards)


# ══════════════════════════════════════════════════════════════
# APP ECOSYSTEM HTML GENERATOR
# ══════════════════════════════════════════════════════════════

def build_present_apps_html(apps):
    """Generate HTML for present apps list from app_ecosystem.json."""
    items = []
    for app in apps:
        quality_icon = "✓" if app.get("quality") == "good" else "⚠"
        quality_title = "Good choice" if app.get("quality") == "good" else "Needs attention"
        notes_html = ""
        if app.get("notes"):
            notes_html = f'\n                                    <div class="app-benchmark-tag">{app["notes"]}</div>'
        items.append(f'''<div class="app-item present">
                                <div class="app-icon">&#10003;</div>
                                <div class="app-item-details">
                                    <div class="app-name">{app["name"]}</div>
                                    <div class="app-category">{app["category"]}</div>{notes_html}
                                </div>
                                <span class="app-quality" title="{quality_title}">{quality_icon}</span>
                            </div>''')
    return "\n                            ".join(items)


def build_missing_apps_html(apps):
    """Generate HTML for missing apps list from app_ecosystem.json."""
    priority_class_map = {"critical": "critical-priority", "recommended": "recommended-priority", "nice-to-have": "nice-to-have-priority"}
    impact_emoji_map = {"revenue": "💰", "conversion": "📈", "retention": "🔄", "experience": "✨"}
    items = []
    for app in apps:
        pcls = priority_class_map.get(app.get("priority", ""), "recommended-priority")
        plabel = app.get("priority", "recommended").title()
        emoji = impact_emoji_map.get(app.get("impact_type", ""), "📈")
        items.append(f'''<div class="app-item missing">
                                <div class="app-icon">&#10007;</div>
                                <div class="app-item-details">
                                    <div class="app-name">{app["name"]} <span class="app-priority-badge {pcls}">{plabel}</span></div>
                                    <div class="app-category">{app["category"]}</div>
                                    <div class="app-impact-tag {app.get("impact_type", "conversion")}">{emoji} {app.get("impact_label", "")}</div>
                                    <div class="app-benchmark-tag">{app.get("benchmark", "")}</div>
                                </div>
                            </div>''')
    return "\n                            ".join(items)


# ══════════════════════════════════════════════════════════════
# MAIN BUILD
# ══════════════════════════════════════════════════════════════

def main():
    # Check template exists
    if not os.path.exists(TEMPLATE):
        print(f"❌ Template not found: {TEMPLATE}")
        sys.exit(1)

    # Check data directory
    if not os.path.exists(DATA_DIR):
        print(f"❌ No data/ directory found at {DATA_DIR}")
        print("   Run the audit phases first to populate data files.")
        print("   See data_schemas.md for the expected file format.")
        sys.exit(1)

    found, missing = check_data_files()
    print(f"📂 Data files: {len(found)}/7 found")
    if missing:
        print(f"   ⚠ Missing: {', '.join(missing)}")
        print(f"   Build will proceed with available data. Missing sections will be empty.")

    # Load all data
    config = load_json("config.json") or {}
    psi = load_json("pagespeed.json") or {}
    traffic = load_json("traffic.json") or {}
    benchmarks = load_json("benchmark_context.json") or {}
    findings = load_json("ux_findings.json") or {}
    tech = load_json("tech_stack.json") or {}
    apps = load_json("app_ecosystem.json") or {}

    # Read template
    with open(TEMPLATE, "r") as f:
        html = f.read()

    # ── Build replacements dict from data files ──────────────
    client_mobile = psi.get("client", {}).get("mobile", {})
    client_crux = psi.get("client", {}).get("crux", {})
    cwv = psi.get("cwv_summary", {})
    proxy = traffic.get("proxy_signals", {})
    ind_bench = config.get("industry_benchmarks", benchmarks.get("funnel_benchmarks", {}))
    counts = findings.get("counts", {})
    health = tech.get("health", {})

    replacements = {
        # Client info (from config.json)
        "{{CLIENT_NAME}}": config.get("brand_name", ""),
        "{{CLIENT_URL}}": config.get("brand_url", ""),
        "{{REPORT_DATE}}": config.get("report_date", datetime.now().strftime("%B %Y")),
        "{{REPORT_PASSWORD}}": config.get("password", ""),
        "{{INDUSTRY_CATEGORY}}": config.get("industry_label", ""),
        "{{INDUSTRY_CATEGORY_SHORT}}": config.get("industry_short", ""),

        # Audit overview (from ux_findings.json counts)
        "{{SEVERITY_CRITICAL_COUNT}}": str(counts.get("critical", "")),
        "{{SEVERITY_IMPORTANT_COUNT}}": str(counts.get("important", "")),
        "{{SEVERITY_OPPORTUNITY_COUNT}}": str(counts.get("opportunity", "")),
        "{{FINDING_COUNT_TOTAL}}": str(counts.get("total", "")),
        "{{COMPETITOR_COUNT}}": str(len(config.get("competitors", []))),
        "{{APPS_PRESENT_COUNT}}": str(apps.get("present_count", "")),
        "{{FINDING_COUNT_HOMEPAGE}}": str(counts.get("homepage", "")),
        "{{FINDING_COUNT_COLLECTION}}": str(counts.get("collection", "")),
        "{{FINDING_COUNT_PDP}}": str(counts.get("pdp", "")),
        "{{FINDING_COUNT_CART}}": str(counts.get("cart", "")),

        # Traffic & proxy signals (from traffic.json)
        "{{PROXY_TIER_NAME}}": proxy.get("tier", ""),
        "{{PROXY_TIER_SESSIONS}}": proxy.get("tier_sessions", ""),
        "{{PROXY_PRODUCT_COUNT}}": proxy.get("product_count", ""),
        "{{PROXY_REVIEW_COUNT}}": proxy.get("review_count", ""),
        "{{PROXY_INSTAGRAM}}": proxy.get("instagram_followers", ""),
        "{{PROXY_APP_COUNT}}": str(proxy.get("app_count", "")),
        "{{PROXY_ESTIMATED_REVENUE}}": str(proxy.get("estimated_revenue", "")),
        "{{PROXY_TIER_NARRATIVE}}": traffic.get("tier_narrative", ""),

        # Industry benchmarks (from config.json or benchmark_context.json)
        "{{INDUSTRY_PDP_VIEW_RATE_P25}}": ind_bench.get("pdp_view_rate", {}).get("p25", ""),
        "{{INDUSTRY_PDP_VIEW_RATE}}": ind_bench.get("pdp_view_rate", {}).get("p50", ""),
        "{{INDUSTRY_PDP_VIEW_RATE_P75}}": ind_bench.get("pdp_view_rate", {}).get("p75", ""),
        "{{INDUSTRY_ATC_RATE_P25}}": ind_bench.get("atc_rate", {}).get("p25", ""),
        "{{INDUSTRY_ATC_RATE}}": ind_bench.get("atc_rate", {}).get("p50", ""),
        "{{INDUSTRY_ATC_RATE_P75}}": ind_bench.get("atc_rate", {}).get("p75", ""),
        "{{INDUSTRY_CART_TO_CHECKOUT_P25}}": ind_bench.get("cart_to_checkout", {}).get("p25", ""),
        "{{INDUSTRY_CART_TO_CHECKOUT}}": ind_bench.get("cart_to_checkout", {}).get("p50", ""),
        "{{INDUSTRY_CART_TO_CHECKOUT_P75}}": ind_bench.get("cart_to_checkout", {}).get("p75", ""),
        "{{INDUSTRY_CHECKOUT_COMPLETION_P25}}": ind_bench.get("checkout_completion", {}).get("p25", ""),
        "{{INDUSTRY_CHECKOUT_COMPLETION}}": ind_bench.get("checkout_completion", {}).get("p50", ""),
        "{{INDUSTRY_CHECKOUT_COMPLETION_P75}}": ind_bench.get("checkout_completion", {}).get("p75", ""),
        "{{INDUSTRY_CVR_P25}}": ind_bench.get("cvr", {}).get("p25", ""),
        "{{INDUSTRY_CVR_P50}}": ind_bench.get("cvr", {}).get("p50", ""),
        "{{INDUSTRY_CVR_P75}}": ind_bench.get("cvr", {}).get("p75", ""),
        "{{INDUSTRY_CVR_P50_RAW}}": ind_bench.get("cvr", {}).get("p50_raw", ""),

        # PageSpeed (from pagespeed.json)
        "{{PS_CLIENT_MOBILE_SCORE}}": str(client_mobile.get("score", "")),
        "{{PS_CLIENT_MOBILE_CLASS}}": client_mobile.get("score_class", ""),
        "{{PS_CLIENT_MOBILE_VERDICT}}": psi.get("verdict", ""),
        "{{PS_CLIENT_LCP}}": client_mobile.get("lcp", ""),
        "{{PS_CLIENT_LCP_CLASS}}": client_mobile.get("lcp_class", ""),
        "{{PS_CLIENT_LCP_STATUS}}": client_mobile.get("lcp_status", ""),
        "{{PS_CLIENT_LCP_LABEL}}": client_mobile.get("lcp_label", client_mobile.get("lcp_status", "").title()),
        "{{PS_CLIENT_FCP}}": client_mobile.get("fcp", ""),
        "{{PS_CLIENT_FCP_CLASS}}": client_mobile.get("fcp_class", ""),
        "{{PS_CLIENT_FCP_STATUS}}": client_mobile.get("fcp_status", ""),
        "{{PS_CLIENT_FCP_LABEL}}": client_mobile.get("fcp_label", client_mobile.get("fcp_status", "").title()),
        "{{PS_CLIENT_TBT}}": client_mobile.get("tbt", ""),
        "{{PS_CLIENT_TBT_CLASS}}": client_mobile.get("tbt_class", ""),
        "{{PS_CLIENT_TBT_STATUS}}": client_mobile.get("tbt_status", ""),
        "{{PS_CLIENT_TBT_LABEL}}": client_mobile.get("tbt_label", client_mobile.get("tbt_status", "").title()),
        "{{PS_CLIENT_CLS}}": client_mobile.get("cls", ""),
        "{{PS_CLIENT_CLS_CLASS}}": client_mobile.get("cls_class", ""),
        "{{PS_CLIENT_CLS_STATUS}}": client_mobile.get("cls_status", ""),
        "{{PS_CLIENT_CLS_LABEL}}": client_mobile.get("cls_label", client_mobile.get("cls_status", "").title()),
        "{{PS_CLIENT_INP}}": client_crux.get("inp", "N/A"),
        "{{PS_CLIENT_INP_CLASS}}": client_crux.get("inp_class", ""),
        "{{PS_CLIENT_INP_STATUS}}": client_crux.get("inp_status", ""),
        "{{PS_CLIENT_INP_LABEL}}": client_crux.get("inp_label", ""),
        "{{CWV_SUMMARY_CLASS}}": cwv.get("class", ""),
        "{{CWV_PASS_ICON}}": cwv.get("icon", ""),
        "{{CWV_PASS_COUNT}}": str(cwv.get("pass_count", "")),
        "{{PS_COMBINED_NARRATIVE}}": psi.get("narrative", ""),

        # Technology (from tech_stack.json)
        "{{TECH_HEALTH_CLASS}}": health.get("class", ""),
        "{{TECH_HEALTH_ICON}}": health.get("icon", ""),
        "{{TECH_HEALTH_SUMMARY}}": health.get("summary", ""),
        "{{TECH_PLATFORM_STATUS}}": tech.get("platform_status", ""),
        "{{TECH_PLATFORM_STATUS_LABEL}}": tech.get("platform_status_label", ""),
        "{{PLATFORM}}": tech.get("platform", ""),
        "{{PLATFORM_NOTES}}": tech.get("platform_notes", ""),
        "{{TECH_THEME_STATUS}}": tech.get("theme", {}).get("status", ""),
        "{{TECH_THEME_STATUS_LABEL}}": tech.get("theme", {}).get("status_label", ""),
        "{{THEME_NAME}}": tech.get("theme", {}).get("name", ""),
        "{{THEME_TYPE}}": tech.get("theme", {}).get("type", ""),
        "{{THEME_VERSION_NOTE}}": tech.get("theme", {}).get("version_note", ""),
        "{{THEME_FEATURE_NOTE}}": tech.get("theme", {}).get("feature_note", ""),
        "{{TECH_CHECKOUT_STATUS}}": tech.get("checkout", {}).get("status", ""),
        "{{TECH_CHECKOUT_STATUS_LABEL}}": tech.get("checkout", {}).get("status_label", ""),
        "{{CHECKOUT_TYPE}}": tech.get("checkout", {}).get("type", ""),
        "{{CHECKOUT_GUEST_NOTE}}": tech.get("checkout", {}).get("guest_note", ""),
        "{{CHECKOUT_EXPRESS_NOTE}}": tech.get("checkout", {}).get("express_note", ""),
        "{{CHECKOUT_FRICTION_NOTE}}": tech.get("checkout", {}).get("friction_note", ""),
        "{{TECH_PAYMENTS_STATUS}}": tech.get("payments", {}).get("status", ""),
        "{{TECH_PAYMENTS_STATUS_LABEL}}": tech.get("payments", {}).get("status_label", ""),
        "{{PAYMENT_GATEWAY}}": tech.get("payments", {}).get("gateway", ""),
        "{{PAYMENT_METHODS_NOTE}}": tech.get("payments", {}).get("methods_note", ""),
        "{{PAYMENT_COD_NOTE}}": tech.get("payments", {}).get("cod_note", ""),
        "{{PAYMENT_BNPL_NOTE}}": tech.get("payments", {}).get("bnpl_note", ""),
        "{{TECH_CDN_STATUS}}": tech.get("cdn", {}).get("status", ""),
        "{{TECH_CDN_STATUS_LABEL}}": tech.get("cdn", {}).get("status_label", ""),
        "{{CDN_PROVIDER}}": tech.get("cdn", {}).get("provider", ""),
        "{{CDN_IMAGE_NOTE}}": tech.get("cdn", {}).get("image_note", ""),
        "{{CDN_COMPRESSION_NOTE}}": tech.get("cdn", {}).get("compression_note", ""),
        "{{CDN_CACHING_NOTE}}": tech.get("cdn", {}).get("caching_note", ""),
        "{{TECH_SECURITY_STATUS}}": tech.get("security", {}).get("status", ""),
        "{{TECH_SECURITY_STATUS_LABEL}}": tech.get("security", {}).get("status_label", ""),
        "{{SECURITY_SSL_STATUS}}": tech.get("security", {}).get("ssl_status", ""),
        "{{SECURITY_HTTPS_NOTE}}": tech.get("security", {}).get("https_note", ""),
        "{{SECURITY_PCI_NOTE}}": tech.get("security", {}).get("pci_note", ""),
        "{{SECURITY_COOKIE_NOTE}}": tech.get("security", {}).get("cookie_note", ""),
        "{{TECH_NARRATIVE}}": tech.get("narrative", ""),

        # App ecosystem (from app_ecosystem.json)
        "{{APPS_MISSING_COUNT}}": str(apps.get("missing_count", "")),
        "{{APPS_BENCHMARK_CONTEXT}}": apps.get("benchmark_context", ""),
        "{{APP_STACK_NARRATIVE}}": apps.get("narrative", ""),

        # Nav reference
        "{{UX_FINDING_1_SHORT_TITLE}}": "UX & Conversion Findings",
    }

    # Apply simple replacements
    for key, val in replacements.items():
        html = html.replace(key, str(val))

    # ── Competition table (from pagespeed.json) ──────────────
    comp_table = psi.get("competition_table_html", "")
    html = html.replace("{{PS_COMPETITION_TABLE_ROWS}}", comp_table)

    # ── Finding cards (from ux_findings.json) ────────────────
    findings_data = findings.get("findings", {})
    hp_cards = build_finding_cards(findings_data.get("homepage", []))
    col_cards = build_finding_cards(findings_data.get("collection", []))
    pdp_cards = build_finding_cards(findings_data.get("pdp", []))
    cart_cards = build_finding_cards(findings_data.get("cart", []))

    html = html.replace("{{FINDING_CARDS_HOMEPAGE}}", hp_cards)
    html = html.replace("{{FINDING_CARDS_COLLECTION}}", col_cards)
    html = html.replace("{{FINDING_CARDS_PDP}}", pdp_cards)
    html = html.replace("{{FINDING_CARDS_CART}}", cart_cards)

    # ── App ecosystem HTML (from app_ecosystem.json) ─────────
    present_html = build_present_apps_html(apps.get("present_apps", []))
    missing_html = build_missing_apps_html(apps.get("missing_apps", []))
    html = html.replace("{{APPS_PRESENT_HTML}}", present_html)
    html = html.replace("{{APPS_MISSING_HTML}}", missing_html)

    # ── Cleanup ──────────────────────────────────────────────
    html = re.sub(r'<!--\s*POPULATE:.*?-->', '', html, flags=re.DOTALL)
    html = re.sub(r'<!--\s*VIDEO FINDING CARD PATTERN.*?-->', '', html, flags=re.DOTALL)
    html = re.sub(r'/\*[^\n]*\{\{[A-Z_]+\}\}[^\n]*\*/', '', html)

    # Verify no template variables remain
    remaining = re.findall(r'\{\{[A-Z_]+\}\}', html)
    if remaining:
        unique = sorted(set(remaining))
        print(f"\n⚠  WARNING: {len(unique)} unreplaced variables found:")
        for v in unique:
            count = remaining.count(v)
            print(f"   {v} (×{count})" if count > 1 else f"   {v}")
    else:
        print("✓ All template variables replaced successfully")

    # Write output
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w") as f:
        f.write(html)

    lines = html.count('\n') + 1
    print(f"✓ Written to {OUTPUT}")
    print(f"  Total lines: {lines}")
    print(f"  File size: {len(html):,} bytes")
    print(f"  Findings: {counts.get('total', '?')} ({counts.get('homepage', '?')} HP + {counts.get('collection', '?')} COL + {counts.get('pdp', '?')} PDP + {counts.get('cart', '?')} CART)")
    print(f"  Apps: {apps.get('present_count', '?')} present, {apps.get('missing_count', '?')} missing")


if __name__ == "__main__":
    main()
