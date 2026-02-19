from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
from mcp.server.fastmcp import FastMCP
from visa_jobs_mcp.pipeline import (
    default_dataset_path,
    discover_latest_dol_disclosure_urls as pipeline_discover_latest_dol_disclosure_urls,
    run_dol_pipeline,
)

try:
    from jobspy import scrape_jobs
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("python-jobspy is required. Install dependencies first.") from exc

mcp = FastMCP("visa-jobs-mcp")

DEFAULT_DATASET_PATH = default_dataset_path()
DEFAULT_SITES = [
    s.strip()
    for s in os.getenv("VISA_JOB_SITES", "linkedin").split(",")
    if s.strip()
]
SUPPORTED_SITES = {"linkedin"}
DEFAULT_INDEED_COUNTRY = os.getenv("VISA_INDEED_COUNTRY", "USA")
DEFAULT_DOL_PERFORMANCE_URL = os.getenv(
    "VISA_DOL_PERFORMANCE_URL",
    "https://www.dol.gov/agencies/eta/foreign-labor/performance",
)
DEFAULT_USER_PREFS_PATH = os.getenv(
    "VISA_USER_PREFS_PATH",
    "data/config/user_preferences.json",
)

VISA_POSITIVE_PATTERNS = [
    r"\bvisa sponsorship\b",
    r"\bsponsor(?:ship|ed|s)?\b",
    r"\bh-?1b\b",
    r"\be-?3\b",
    r"\bopt\b",
    r"\bcpt\b",
    r"\bgreen card\b",
]

VISA_NEGATIVE_PATTERNS = [
    r"\bno visa sponsorship\b",
    r"\bwithout visa sponsorship\b",
    r"\bdo not sponsor\b",
    r"\bunable to sponsor\b",
    r"\bmust be authorized to work\b",
]

CANONICAL_COLUMNS = {
    "company_tier": ["company_tier", "size"],
    "company_name": ["company_name", "EMPLOYER"],
    "h1b": ["h1b", "H-1B"],
    "h1b1_chile": ["h1b1_chile", "H-1B1 Chile"],
    "h1b1_singapore": ["h1b1_singapore", "H-1B1 Singapore"],
    "e3_australian": ["e3_australian", "E-3 Australian"],
    "green_card": ["green_card", "Green Card"],
    "email_1": ["email_1", "EMAIL_1"],
    "email_1_date": ["email_1_date", "EMAIL_1_DATE"],
    "contact_1": ["contact_1", "CONTACT_1"],
    "contact_1_title": ["contact_1_title", "CONTACT_1_TITLE"],
    "contact_1_phone": ["contact_1_phone", "CONTACT_1_PHONE"],
    "email_2": ["email_2", "EMAIL_2"],
    "email_2_date": ["email_2_date", "EMAIL_2_DATE"],
    "contact_2": ["contact_2", "CONTACT_2"],
    "contact_2_title": ["contact_2_title", "CONTACT_2_TITLE"],
    "contact_2_phone": ["contact_2_phone", "CONTACT_2_PHONE"],
    "email_3": ["email_3", "EMAIL_3"],
    "email_3_date": ["email_3_date", "EMAIL_3_DATE"],
    "contact_3": ["contact_3", "CONTACT_3"],
    "contact_3_title": ["contact_3_title", "CONTACT_3_TITLE"],
    "contact_3_phone": ["contact_3_phone", "CONTACT_3_PHONE"],
}

LEGAL_SUFFIXES = (
    "inc",
    "corp",
    "corporation",
    "co",
    "llc",
    "ltd",
    "lp",
    "plc",
    "pc",
    "holdings",
    "holding",
    "group",
    "technologies",
    "technology",
)

VISA_TYPE_ALIASES = {
    "h1b": "h1b",
    "h-1b": "h1b",
    "h1b1_chile": "h1b1_chile",
    "h-1b1 chile": "h1b1_chile",
    "h1b1 chile": "h1b1_chile",
    "h1b1_chile/singapore": "h1b1_chile",
    "h1b1_singapore": "h1b1_singapore",
    "h-1b1 singapore": "h1b1_singapore",
    "h1b1 singapore": "h1b1_singapore",
    "e3": "e3_australian",
    "e-3": "e3_australian",
    "e3_australian": "e3_australian",
    "e-3 australian": "e3_australian",
    "green_card": "green_card",
    "green card": "green_card",
    "perm": "green_card",
}

VISA_TYPE_LABELS = {
    "h1b": "H-1B",
    "h1b1_chile": "H-1B1 Chile",
    "h1b1_singapore": "H-1B1 Singapore",
    "e3_australian": "E-3 Australian",
    "green_card": "Green Card",
}



@dataclass
class CompanySponsorStats:
    company_name: str
    company_tier: str
    h1b: int
    h1b1_chile: int
    h1b1_singapore: int
    e3_australian: int
    green_card: int
    total_visas: int
    email_1: str
    contact_1: str
    contact_1_title: str
    contact_1_phone: str


@dataclass
class EvaluatedJob:
    title: str
    company: str
    location: str
    site: str
    date_posted: str | None
    job_url: str
    description_snippet: str
    matched_via_company_dataset: bool
    matched_via_job_description: bool
    rejected_for_no_sponsorship_phrase: bool
    sponsorship_reasons: list[str]
    employer_contacts: list[dict[str, str]]
    visa_counts: dict[str, int]
    visas_sponsored: list[str]
    matches_user_visa_preferences: bool
    sponsor_stats: dict[str, Any] | None


def _disable_proxies() -> None:
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        os.environ.pop(key, None)


def _normalize_visa_type(value: str) -> str:
    key = value.strip().lower()
    if key not in VISA_TYPE_ALIASES:
        raise ValueError(
            f"Unsupported visa type '{value}'. Use one of: {sorted(set(VISA_TYPE_ALIASES.values()))}"
        )
    return VISA_TYPE_ALIASES[key]


def _load_user_prefs(path: str = DEFAULT_USER_PREFS_PATH) -> dict[str, Any]:
    pref_file = Path(path)
    if not pref_file.exists():
        return {}
    try:
        return json.loads(pref_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_user_prefs(data: dict[str, Any], path: str = DEFAULT_USER_PREFS_PATH) -> None:
    pref_file = Path(path)
    pref_file.parent.mkdir(parents=True, exist_ok=True)
    pref_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _get_required_user_visa_types(user_id: str) -> list[str]:
    uid = user_id.strip()
    if not uid:
        raise ValueError(
            "user_id is required. Set visa preferences first using set_user_preferences."
        )
    prefs = _load_user_prefs()
    user = prefs.get(uid)
    if not user:
        raise ValueError(
            f"No saved preferences for user_id='{uid}'. Set visa preferences first using set_user_preferences."
        )
    stored = user.get("preferred_visa_types", [])
    if not stored:
        raise ValueError(
            f"user_id='{uid}' has no preferred_visa_types. Set visa preferences first using set_user_preferences."
        )
    return sorted({_normalize_visa_type(v) for v in stored})


def normalize_company_name(name: str | None) -> str:
    if not name:
        return ""
    text = str(name).strip()
    if text.lower() in {"nan", "none", "null", "na", "n/a"}:
        return ""
    cleaned = re.sub(r"[^A-Za-z0-9\s]", " ", text.lower())
    tokens = [t for t in cleaned.split() if t]
    while tokens and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def _detect_visa_signals(description: str) -> tuple[bool, bool, list[str]]:
    text = (description or "").lower()
    positive_hits = [p for p in VISA_POSITIVE_PATTERNS if re.search(p, text)]
    negative_hits = [p for p in VISA_NEGATIVE_PATTERNS if re.search(p, text)]
    return bool(positive_hits), bool(negative_hits), positive_hits + negative_hits


def _canonicalize_company_df(df: pd.DataFrame) -> pd.DataFrame:
    rename_map: dict[str, str] = {}
    for canonical, options in CANONICAL_COLUMNS.items():
        for option in options:
            if option in df.columns:
                rename_map[option] = canonical
                break
    cdf = df.rename(columns=rename_map).copy()

    required = [
        "company_tier",
        "company_name",
        "h1b",
        "h1b1_chile",
        "h1b1_singapore",
        "e3_australian",
        "green_card",
    ]
    missing = [c for c in required if c not in cdf.columns]
    if missing:
        raise ValueError(f"Dataset missing required columns: {missing}")

    for col in ("h1b", "h1b1_chile", "h1b1_singapore", "e3_australian", "green_card"):
        cdf[col] = pd.to_numeric(cdf[col], errors="coerce").fillna(0).astype(int)

    cdf["company_name"] = cdf["company_name"].astype(str).str.strip()
    cdf["normalized_company"] = cdf["company_name"].map(normalize_company_name)
    cdf = cdf[cdf["normalized_company"] != ""].copy()

    cdf["total_visas"] = (
        cdf["h1b"]
        + cdf["h1b1_chile"]
        + cdf["h1b1_singapore"]
        + cdf["e3_australian"]
        + cdf["green_card"]
    )

    # Keep strongest sponsor entry when duplicates normalize to same value.
    cdf = cdf.sort_values(["total_visas"], ascending=False).drop_duplicates(
        subset=["normalized_company"], keep="first"
    )
    return cdf


@lru_cache(maxsize=4)
def _load_company_dataset(dataset_path: str) -> pd.DataFrame:
    if not os.path.exists(dataset_path):
        raise FileNotFoundError(
            f"Dataset not found at '{dataset_path}'. Set VISA_COMPANY_DATASET_PATH correctly."
        )
    raw = pd.read_csv(dataset_path)
    return _canonicalize_company_df(raw)


def _ensure_dataset_exists(dataset_path: str) -> None:
    if os.path.exists(dataset_path):
        return
    run_dol_pipeline(output_path=dataset_path, performance_url=DEFAULT_DOL_PERFORMANCE_URL)
    _load_company_dataset.cache_clear()


def _extract_text(row: pd.Series, key: str) -> str:
    value = row.get(key, "")
    if pd.isna(value):
        return ""
    return str(value).strip()


def _job_date(row: pd.Series) -> str | None:
    raw = row.get("date_posted")
    if raw is None or pd.isna(raw):
        return None
    try:
        dt = pd.to_datetime(raw, errors="coerce")
    except Exception:
        return str(raw)
    if pd.isna(dt):
        return str(raw)
    return dt.isoformat()


def _company_stats(company_row: pd.Series) -> CompanySponsorStats:
    return CompanySponsorStats(
        company_name=_extract_text(company_row, "company_name"),
        company_tier=_extract_text(company_row, "company_tier"),
        h1b=int(company_row.get("h1b", 0)),
        h1b1_chile=int(company_row.get("h1b1_chile", 0)),
        h1b1_singapore=int(company_row.get("h1b1_singapore", 0)),
        e3_australian=int(company_row.get("e3_australian", 0)),
        green_card=int(company_row.get("green_card", 0)),
        total_visas=int(company_row.get("total_visas", 0)),
        email_1=_extract_text(company_row, "email_1"),
        contact_1=_extract_text(company_row, "contact_1"),
        contact_1_title=_extract_text(company_row, "contact_1_title"),
        contact_1_phone=_extract_text(company_row, "contact_1_phone"),
    )


def _company_contacts(company_row: pd.Series) -> list[dict[str, str]]:
    contacts: list[dict[str, str]] = []
    for i in (1, 2, 3):
        name = _extract_text(company_row, f"contact_{i}")
        title = _extract_text(company_row, f"contact_{i}_title")
        email = _extract_text(company_row, f"email_{i}")
        phone = _extract_text(company_row, f"contact_{i}_phone")
        if not any([name, title, email, phone]):
            continue
        contacts.append(
            {
                "name": name,
                "title": title,
                "email": email,
                "phone": phone,
            }
        )
    return contacts


def _visa_counts_from_company_row(company_row: pd.Series) -> dict[str, int]:
    counts = {
        "h1b": int(company_row.get("h1b", 0)),
        "h1b1_chile": int(company_row.get("h1b1_chile", 0)),
        "h1b1_singapore": int(company_row.get("h1b1_singapore", 0)),
        "e3_australian": int(company_row.get("e3_australian", 0)),
        "green_card": int(company_row.get("green_card", 0)),
    }
    counts["total_visas"] = sum(counts.values())
    return counts


def _visa_types_from_description(description: str) -> set[str]:
    text = (description or "").lower()
    found: set[str] = set()
    if re.search(r"\bh-?1b\b", text):
        found.add("h1b")
    if re.search(r"\bh-?1b1\b", text) and re.search(r"\bchile\b", text):
        found.add("h1b1_chile")
    if re.search(r"\bh-?1b1\b", text) and re.search(r"\bsingapore\b", text):
        found.add("h1b1_singapore")
    if re.search(r"\be-?3\b", text):
        found.add("e3_australian")
    if re.search(r"\bgreen card\b", text) or re.search(r"\bperm\b", text):
        found.add("green_card")
    return found


@mcp.tool()
def discover_latest_dol_disclosure_urls(
    performance_url: str = DEFAULT_DOL_PERFORMANCE_URL,
) -> dict[str, Any]:
    """Discover latest LCA and PERM disclosure xlsx URLs from DOL performance page."""
    return pipeline_discover_latest_dol_disclosure_urls(performance_url=performance_url)


@mcp.tool()
def build_company_dataset_from_dol_disclosures(
    output_path: str = DEFAULT_DATASET_PATH,
    lca_path_or_url: str = "",
    perm_path_or_url: str = "",
    performance_url: str = DEFAULT_DOL_PERFORMANCE_URL,
) -> dict[str, Any]:
    """Build canonical sponsor-company dataset from DOL LCA + PERM disclosure files."""
    result = run_dol_pipeline(
        output_path=output_path,
        lca_path_or_url=lca_path_or_url,
        perm_path_or_url=perm_path_or_url,
        performance_url=performance_url,
    )

    _load_company_dataset.cache_clear()

    return {
        "output_path": result.output_path,
        "rows_written": result.rows_written,
        "lca_source": result.lca_source,
        "perm_source": result.perm_source,
        "lca_employer_col": result.lca_employer_col,
        "lca_visa_col": result.lca_visa_col,
        "perm_employer_col": result.perm_employer_col,
        "discovered_from_performance_url": result.discovered_from_performance_url,
        "manifest_path": result.manifest_path,
        "run_at_utc": result.run_at_utc,
    }


@mcp.tool()
def run_internal_dol_pipeline(
    output_path: str = DEFAULT_DATASET_PATH,
    lca_path_or_url: str = "",
    perm_path_or_url: str = "",
    performance_url: str = DEFAULT_DOL_PERFORMANCE_URL,
) -> dict[str, Any]:
    """Internal pipeline: discover/pull DOL data and rebuild canonical sponsorship CSV."""
    result = run_dol_pipeline(
        output_path=output_path,
        lca_path_or_url=lca_path_or_url,
        perm_path_or_url=perm_path_or_url,
        performance_url=performance_url,
    )
    _load_company_dataset.cache_clear()
    return {
        "output_path": result.output_path,
        "rows_written": result.rows_written,
        "lca_source": result.lca_source,
        "perm_source": result.perm_source,
        "manifest_path": result.manifest_path,
        "run_at_utc": result.run_at_utc,
    }


@mcp.tool()
def set_user_preferences(
    user_id: str,
    preferred_visa_types: list[str],
) -> dict[str, Any]:
    """Save persistent user preferences for visa search filtering."""
    if not user_id.strip():
        raise ValueError("user_id is required")
    normalized_types = sorted({_normalize_visa_type(v) for v in preferred_visa_types})
    prefs = _load_user_prefs()
    prefs[user_id] = {
        "preferred_visa_types": normalized_types,
    }
    _save_user_prefs(prefs)
    return {"user_id": user_id, "preferences": prefs[user_id], "path": DEFAULT_USER_PREFS_PATH}


@mcp.tool()
def get_user_preferences(user_id: str) -> dict[str, Any]:
    """Get persisted user preferences."""
    if not user_id.strip():
        raise ValueError("user_id is required")
    prefs = _load_user_prefs()
    return {
        "user_id": user_id,
        "preferences": prefs.get(user_id, {}),
        "path": DEFAULT_USER_PREFS_PATH,
    }


@mcp.tool()
def find_visa_sponsored_jobs(
    location: str,
    job_title: str,
    user_id: str,
    results_wanted: int = 300,
    hours_old: int = 336,
    dataset_path: str = DEFAULT_DATASET_PATH,
    sites: list[str] | None = None,
    max_returned: int = 10,
    offset: int = 0,
    require_description_signal: bool = False,
) -> dict[str, Any]:
    """Search jobs by area with JobSpy, then keep jobs likely to sponsor visas.

    This uses the flipped model:
    1) Scrape jobs in an area across multiple sites.
    2) Match scraped companies against the sponsorship dataset.
    3) Also accept jobs when description contains visa sponsorship signals.
    """
    if not location.strip():
        raise ValueError("location is required")
    if not job_title.strip():
        raise ValueError("job_title is required")

    _disable_proxies()
    _ensure_dataset_exists(dataset_path)

    sponsor_df = _load_company_dataset(dataset_path).set_index("normalized_company", drop=False)
    requested_sites = sites or DEFAULT_SITES
    invalid_sites = [s for s in requested_sites if s not in SUPPORTED_SITES]
    if invalid_sites:
        raise ValueError(f"Only LinkedIn is supported right now. Invalid sites: {invalid_sites}")
    chosen_sites = ["linkedin"]
    desired_visa_types = _get_required_user_visa_types(user_id)

    raw_jobs = scrape_jobs(
        site_name=chosen_sites,
        search_term=job_title,
        location=location,
        results_wanted=results_wanted,
        hours_old=hours_old,
        country_indeed=DEFAULT_INDEED_COUNTRY,
    )

    if raw_jobs is None or raw_jobs.empty:
        return {
            "query": {
                "location": location,
                "job_title": job_title,
                "sites": chosen_sites,
                "dataset_path": dataset_path,
            },
            "stats": {
                "scraped_jobs": 0,
                "accepted_jobs": 0,
            },
            "jobs": [],
        }

    results: list[EvaluatedJob] = []

    for _, row in raw_jobs.iterrows():
        company = _extract_text(row, "company")
        normalized = normalize_company_name(company)
        description = _extract_text(row, "description")
        title = _extract_text(row, "title")
        job_url = _extract_text(row, "job_url")
        site = _extract_text(row, "site")
        job_location = _extract_text(row, "location")

        has_positive, has_negative, hits = _detect_visa_signals(description)

        sponsor_stats = None
        visa_counts: dict[str, int] = {}
        visas_sponsored: list[str] = []
        matches_user_visa_preferences = False
        matched_company = False
        if normalized and normalized in sponsor_df.index:
            company_row = sponsor_df.loc[normalized]
            sponsor_stats = _company_stats(company_row)
            visa_counts = _visa_counts_from_company_row(company_row)
            visas_sponsored = [
                VISA_TYPE_LABELS[k] for k in ("h1b", "h1b1_chile", "h1b1_singapore", "e3_australian", "green_card")
                if visa_counts.get(k, 0) > 0
            ]
            matched_company = sponsor_stats.total_visas > 0
            if desired_visa_types:
                matches_user_visa_preferences = any(
                    visa_counts.get(v, 0) > 0 for v in desired_visa_types
                )

        rejected_for_negative = has_negative
        desc_visa_types = _visa_types_from_description(description)
        if desired_visa_types and desc_visa_types.intersection(set(desired_visa_types)):
            matches_user_visa_preferences = True

        accept = False
        if not rejected_for_negative:
            if require_description_signal:
                accept = has_positive
            else:
                accept = matched_company or has_positive
            if desired_visa_types:
                accept = accept and matches_user_visa_preferences

        if not accept:
            continue

        results.append(
            EvaluatedJob(
                title=title,
                company=company,
                location=job_location,
                site=site,
                date_posted=_job_date(row),
                job_url=job_url,
                description_snippet=description[:350],
                matched_via_company_dataset=matched_company,
                matched_via_job_description=has_positive,
                rejected_for_no_sponsorship_phrase=rejected_for_negative,
                sponsorship_reasons=hits,
                employer_contacts=_company_contacts(sponsor_df.loc[normalized]) if matched_company else [],
                visa_counts=visa_counts,
                visas_sponsored=visas_sponsored,
                matches_user_visa_preferences=matches_user_visa_preferences,
                sponsor_stats=asdict(sponsor_stats) if sponsor_stats else None,
            )
        )

    limited = results[offset : offset + max_returned]

    return {
        "query": {
            "location": location,
            "job_title": job_title,
            "sites": chosen_sites,
            "results_wanted": results_wanted,
            "hours_old": hours_old,
            "dataset_path": dataset_path,
            "offset": offset,
            "user_id": user_id,
            "preferred_visa_types": desired_visa_types,
            "require_description_signal": require_description_signal,
            "proxies_used": False,
        },
        "stats": {
            "scraped_jobs": int(len(raw_jobs)),
            "accepted_jobs": int(len(results)),
            "returned_jobs": int(len(limited)),
        },
        "jobs": [asdict(job) for job in limited],
    }


@mcp.tool()
def refresh_company_dataset_cache(dataset_path: str = DEFAULT_DATASET_PATH) -> dict[str, Any]:
    """Clear and reload cached sponsorship dataset."""
    _ensure_dataset_exists(dataset_path)
    _load_company_dataset.cache_clear()
    df = _load_company_dataset(dataset_path)
    return {
        "dataset_path": dataset_path,
        "rows": int(len(df)),
        "distinct_normalized_companies": int(df["normalized_company"].nunique()),
    }


def main() -> None:
    _disable_proxies()
    mcp.run()


if __name__ == "__main__":
    main()
