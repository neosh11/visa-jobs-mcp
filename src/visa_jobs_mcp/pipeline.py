from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests

DEFAULT_CANONICAL_DATASET_PATH = "data/companies.csv"


def default_dataset_path() -> str:
    explicit = os.getenv("VISA_COMPANY_DATASET_PATH")
    if explicit:
        return explicit
    return DEFAULT_CANONICAL_DATASET_PATH


DEFAULT_DOL_PERFORMANCE_URL = os.getenv(
    "VISA_DOL_PERFORMANCE_URL",
    "https://www.dol.gov/agencies/eta/foreign-labor/performance",
)
DEFAULT_RAW_DIR = os.getenv("VISA_DOL_RAW_DIR", "data/raw/dol")
DEFAULT_MANIFEST_PATH = os.getenv("VISA_DOL_MANIFEST_PATH", "data/pipeline/last_run.json")

DOL_LINK_PATTERN = re.compile(r'href="([^"]+)"', re.IGNORECASE)

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


@dataclass
class PipelineResult:
    output_path: str
    rows_written: int
    lca_source: str
    perm_source: str
    lca_employer_col: str
    lca_visa_col: str | None
    perm_employer_col: str
    discovered_from_performance_url: bool
    run_at_utc: str
    manifest_path: str
    quality_summary: dict[str, Any]


def disable_proxies() -> None:
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        os.environ.pop(key, None)


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


def discover_latest_dol_disclosure_urls(performance_url: str = DEFAULT_DOL_PERFORMANCE_URL) -> dict[str, Any]:
    disable_proxies()
    resp = requests.get(performance_url, timeout=30)
    resp.raise_for_status()
    html = resp.text

    hrefs = [m for m in DOL_LINK_PATTERN.findall(html)]
    lca_candidates = [
        urljoin(performance_url, h)
        for h in hrefs
        if "LCA_Disclosure_Data_FY" in h and h.lower().endswith(".xlsx")
    ]
    perm_candidates = [
        urljoin(performance_url, h)
        for h in hrefs
        if "PERM_Disclosure_Data" in h and h.lower().endswith(".xlsx")
    ]

    if not lca_candidates or not perm_candidates:
        raise ValueError("Could not discover LCA/PERM disclosure links from DOL page.")

    return {
        "performance_url": performance_url,
        "lca_latest_url": lca_candidates[0],
        "perm_latest_url": perm_candidates[0],
        "lca_candidates_found": lca_candidates[:5],
        "perm_candidates_found": perm_candidates[:5],
    }


def _pick_first_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for col in candidates:
        if col in df.columns:
            return col
    return None


def _count_by_employer(df: pd.DataFrame, employer_col: str) -> pd.DataFrame:
    data = df[[employer_col]].copy()
    data["company_name"] = data[employer_col].astype(str).str.strip()
    data["normalized_company"] = data["company_name"].map(normalize_company_name)
    data = data[data["normalized_company"] != ""]
    grouped = (
        data.groupby(["normalized_company", "company_name"], as_index=False)
        .size()
        .rename(columns={"size": "count"})
    )
    return grouped.sort_values("count", ascending=False).drop_duplicates(
        subset=["normalized_company"], keep="first"
    )


def _count_lca_visa_type(
    lca_df: pd.DataFrame, visa_label: str, visa_col: str, employer_col: str
) -> dict[str, int]:
    filtered = lca_df[lca_df[visa_col].astype(str).str.strip().str.lower() == visa_label.lower()]
    if filtered.empty:
        return {}
    temp = filtered[[employer_col]].copy()
    temp["company_name"] = temp[employer_col].astype(str).str.strip()
    temp["normalized_company"] = temp["company_name"].map(normalize_company_name)
    temp = temp[temp["normalized_company"] != ""]
    grouped = temp.groupby("normalized_company", as_index=False).size()
    return dict(zip(grouped["normalized_company"], grouped["size"]))


def _read_table(path_or_url: str) -> pd.DataFrame:
    if path_or_url.lower().endswith(".csv"):
        return pd.read_csv(path_or_url)
    return pd.read_excel(path_or_url)


def _clean_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "null", "na", "n/a"}:
        return ""
    return text


def _get_col(df: pd.DataFrame, col: str) -> pd.Series:
    if col and col in df.columns:
        return df[col]
    return pd.Series([""] * len(df), index=df.index)


def _extract_contacts(
    df: pd.DataFrame, employer_col: str, specs: list[dict[str, str]]
) -> dict[str, list[dict[str, str]]]:
    base = pd.DataFrame(index=df.index)
    base["normalized_company"] = _get_col(df, employer_col).map(normalize_company_name)
    base = base[base["normalized_company"] != ""]

    all_contacts: list[pd.DataFrame] = []

    for spec in specs:
        part = pd.DataFrame(index=df.index)
        part["normalized_company"] = _get_col(df, employer_col).map(normalize_company_name)

        if spec.get("name_col"):
            part["name"] = _get_col(df, spec["name_col"]).map(_clean_text)
        else:
            first = _get_col(df, spec.get("first_name_col", "")).map(_clean_text)
            middle = _get_col(df, spec.get("middle_name_col", "")).map(_clean_text)
            last = _get_col(df, spec.get("last_name_col", "")).map(_clean_text)
            part["name"] = (first + " " + middle + " " + last).str.replace(r"\s+", " ", regex=True).str.strip()

        part["title"] = _get_col(df, spec.get("title_col", "")).map(_clean_text)
        if spec.get("default_title"):
            part.loc[part["title"] == "", "title"] = spec["default_title"]

        part["email"] = _get_col(df, spec.get("email_col", "")).map(_clean_text)
        phone = _get_col(df, spec.get("phone_col", "")).map(_clean_text)
        phone_ext = _get_col(df, spec.get("phone_ext_col", "")).map(_clean_text)
        part["phone"] = phone
        ext_mask = phone_ext != ""
        part.loc[ext_mask, "phone"] = part.loc[ext_mask, "phone"] + " x" + phone_ext[ext_mask]
        part["source"] = spec.get("source", "unknown")

        part = part[part["normalized_company"] != ""]
        part = part[(part["email"] != "") | (part["phone"] != "") | (part["name"] != "")]
        if part.empty:
            continue

        part["has_email"] = (part["email"] != "").astype(int)
        part["has_phone"] = (part["phone"] != "").astype(int)
        part = part.sort_values(["has_email", "has_phone"], ascending=False)
        part = part.drop_duplicates(
            subset=["normalized_company", "name", "title", "email", "phone"], keep="first"
        )
        all_contacts.append(part[["normalized_company", "name", "title", "email", "phone", "source", "has_email", "has_phone"]])

    if not all_contacts:
        return {}

    contacts_df = pd.concat(all_contacts, ignore_index=True)
    contacts_df = contacts_df.sort_values(["normalized_company", "has_email", "has_phone"], ascending=[True, False, False])

    out: dict[str, list[dict[str, str]]] = {}
    for norm, group in contacts_df.groupby("normalized_company", sort=False):
        rows = []
        for _, r in group.head(3).iterrows():
            rows.append(
                {
                    "name": _clean_text(r["name"]),
                    "title": _clean_text(r["title"]),
                    "email": _clean_text(r["email"]),
                    "phone": _clean_text(r["phone"]),
                    "source": _clean_text(r["source"]),
                }
            )
        out[norm] = rows
    return out


def _quality_summary(df: pd.DataFrame) -> dict[str, Any]:
    visa_cols = ["h1b", "h1b1_chile", "h1b1_singapore", "e3_australian", "green_card"]
    contact_1 = df["contact_1"] if "contact_1" in df.columns else pd.Series([""] * len(df), index=df.index)
    email_1 = df["email_1"] if "email_1" in df.columns else pd.Series([""] * len(df), index=df.index)
    normalized = df["company_name"].map(normalize_company_name)
    summary = {
        "rows": int(len(df)),
        "unique_company_names": int(df["company_name"].nunique()),
        "duplicate_normalized_companies": int(normalized.duplicated().sum()),
        "blank_company_names": int((df["company_name"].fillna("").astype(str).str.strip() == "").sum()),
        "negative_visa_values": int((df[visa_cols] < 0).sum().sum()),
        "visa_type_nonzero_counts": {c: int((df[c] > 0).sum()) for c in visa_cols},
        "visa_type_totals": {c: int(df[c].sum()) for c in visa_cols},
        "total_visa_sum": int(df[visa_cols].sum().sum()),
        "contact_1_nonblank": int((contact_1.fillna("").astype(str).str.strip() != "").sum()),
        "email_1_nonblank": int((email_1.fillna("").astype(str).str.strip() != "").sum()),
    }

    errors: list[str] = []
    warnings: list[str] = []

    if summary["rows"] == 0:
        errors.append("No rows produced")
    elif summary["rows"] < 1000:
        warnings.append("Low row count (<1000) for national disclosure aggregation")
    if summary["duplicate_normalized_companies"] > 0:
        errors.append("Duplicate normalized company names found in output")
    if summary["blank_company_names"] > 0:
        errors.append("Blank company names found in output")
    if summary["negative_visa_values"] > 0:
        errors.append("Negative visa count values found in output")
    if summary["total_visa_sum"] == 0:
        errors.append("All visa counts are zero")

    summary["validation"] = {
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }
    return summary


def _download_if_remote(source: str, raw_dir: str) -> str:
    if not source.lower().startswith(("http://", "https://")):
        return source

    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    raw_base = Path(raw_dir) / ts
    raw_base.mkdir(parents=True, exist_ok=True)

    name = Path(urlparse(source).path).name or "source.xlsx"
    out = raw_base / name

    with requests.get(source, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        with out.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)

    return str(out)


def run_dol_pipeline(
    output_path: str,
    lca_path_or_url: str = "",
    perm_path_or_url: str = "",
    performance_url: str = DEFAULT_DOL_PERFORMANCE_URL,
    raw_dir: str = DEFAULT_RAW_DIR,
    manifest_path: str = DEFAULT_MANIFEST_PATH,
    strict_validation: bool = True,
) -> PipelineResult:
    disable_proxies()

    if not lca_path_or_url or not perm_path_or_url:
        discovered = discover_latest_dol_disclosure_urls(performance_url)
        lca_path_or_url = lca_path_or_url or discovered["lca_latest_url"]
        perm_path_or_url = perm_path_or_url or discovered["perm_latest_url"]
        discovered_from_page = True
    else:
        discovered_from_page = False

    lca_local = _download_if_remote(lca_path_or_url, raw_dir)
    perm_local = _download_if_remote(perm_path_or_url, raw_dir)

    lca_df = _read_table(lca_local)
    perm_df = _read_table(perm_local)

    lca_employer_col = _pick_first_column(
        lca_df, ["EMPLOYER_NAME", "EMPLOYER", "EMPLOYER BUSINESS NAME", "Employer Name"]
    )
    lca_visa_col = _pick_first_column(
        lca_df, ["VISA_CLASS", "CASE_VISA_CLASS", "VISA CLASS", "Visa Class"]
    )
    perm_employer_col = _pick_first_column(
        perm_df,
        [
            "EMPLOYER_NAME",
            "EMP_BUSINESS_NAME",
            "EMPLOYER",
            "EMPLOYER BUSINESS NAME",
            "Employer Name",
        ],
    )

    if not lca_employer_col:
        raise ValueError("LCA file missing employer column")
    if not perm_employer_col:
        raise ValueError("PERM file missing employer column")

    lca_contacts = _extract_contacts(
        lca_df,
        lca_employer_col,
        [
            {
                "first_name_col": "EMPLOYER_POC_FIRST_NAME",
                "middle_name_col": "EMPLOYER_POC_MIDDLE_NAME",
                "last_name_col": "EMPLOYER_POC_LAST_NAME",
                "title_col": "EMPLOYER_POC_JOB_TITLE",
                "email_col": "EMPLOYER_POC_EMAIL",
                "phone_col": "EMPLOYER_POC_PHONE",
                "phone_ext_col": "EMPLOYER_POC_PHONE_EXT",
                "source": "lca_employer_poc",
            },
            {
                "first_name_col": "AGENT_ATTORNEY_FIRST_NAME",
                "middle_name_col": "AGENT_ATTORNEY_MIDDLE_NAME",
                "last_name_col": "AGENT_ATTORNEY_LAST_NAME",
                "email_col": "AGENT_ATTORNEY_EMAIL_ADDRESS",
                "phone_col": "AGENT_ATTORNEY_PHONE",
                "phone_ext_col": "AGENT_ATTORNEY_PHONE_EXT",
                "default_title": "Attorney/Agent",
                "source": "lca_attorney",
            },
            {
                "first_name_col": "PREPARER_FIRST_NAME",
                "last_name_col": "PREPARER_LAST_NAME",
                "email_col": "PREPARER_EMAIL",
                "default_title": "Preparer",
                "source": "lca_preparer",
            },
        ],
    )
    perm_contacts = _extract_contacts(
        perm_df,
        perm_employer_col,
        [
            {
                "first_name_col": "EMP_POC_FIRST_NAME",
                "middle_name_col": "EMP_POC_MIDDLE_NAME",
                "last_name_col": "EMP_POC_LAST_NAME",
                "title_col": "EMP_POC_JOB_TITLE",
                "email_col": "EMP_POC_EMAIL",
                "phone_col": "EMP_POC_PHONE",
                "phone_ext_col": "EMP_POC_PHONEEXT",
                "source": "perm_employer_poc",
            },
            {
                "first_name_col": "ATTY_AG_FIRST_NAME",
                "middle_name_col": "ATTY_AG_MIDDLE_NAME",
                "last_name_col": "ATTY_AG_LAST_NAME",
                "email_col": "ATTY_AG_EMAIL",
                "phone_col": "ATTY_AG_PHONE",
                "phone_ext_col": "ATTY_AG_PHONE_EXT",
                "default_title": "Attorney/Agent",
                "source": "perm_attorney",
            },
            {
                "first_name_col": "DECL_PREP_FIRST_NAME",
                "middle_name_col": "DECL_PREP_MIDDLE_NAME",
                "last_name_col": "DECL_PREP_LAST_NAME",
                "email_col": "DECL_PREP_EMAIL",
                "default_title": "Preparer",
                "source": "perm_preparer",
            },
        ],
    )

    lca_companies = _count_by_employer(lca_df, lca_employer_col)
    perm_companies = _count_by_employer(perm_df, perm_employer_col)

    if lca_visa_col:
        h1b_counts = _count_lca_visa_type(lca_df, "H-1B", lca_visa_col, lca_employer_col)
        h1b1_chile_counts = _count_lca_visa_type(lca_df, "H-1B1 Chile", lca_visa_col, lca_employer_col)
        h1b1_singapore_counts = _count_lca_visa_type(lca_df, "H-1B1 Singapore", lca_visa_col, lca_employer_col)
        e3_counts = _count_lca_visa_type(lca_df, "E-3 Australian", lca_visa_col, lca_employer_col)
    else:
        h1b_counts = dict(zip(lca_companies["normalized_company"], lca_companies["count"]))
        h1b1_chile_counts = {}
        h1b1_singapore_counts = {}
        e3_counts = {}

    perm_counts = dict(zip(perm_companies["normalized_company"], perm_companies["count"]))
    lca_name_map = dict(zip(lca_companies["normalized_company"], lca_companies["company_name"]))
    perm_name_map = dict(zip(perm_companies["normalized_company"], perm_companies["company_name"]))

    all_keys = set(lca_name_map).union(set(perm_name_map))

    rows: list[dict[str, Any]] = []
    for key in sorted(all_keys):
        company_name = lca_name_map.get(key) or perm_name_map.get(key) or key.upper()
        h1b = int(h1b_counts.get(key, 0))
        h1b1_chile = int(h1b1_chile_counts.get(key, 0))
        h1b1_singapore = int(h1b1_singapore_counts.get(key, 0))
        e3 = int(e3_counts.get(key, 0))
        green_card = int(perm_counts.get(key, 0))

        if h1b + h1b1_chile + h1b1_singapore + e3 + green_card == 0:
            continue

        rows.append(
            {
                "company_tier": "dol",
                "company_name": company_name,
                "h1b": h1b,
                "h1b1_chile": h1b1_chile,
                "h1b1_singapore": h1b1_singapore,
                "e3_australian": e3,
                "green_card": green_card,
                "email_1": "",
                "email_1_date": "",
                "contact_1": "",
                "contact_1_title": "",
                "contact_1_phone": "",
                "email_2": "",
                "email_2_date": "",
                "contact_2": "",
                "contact_2_title": "",
                "contact_2_phone": "",
                "email_3": "",
                "email_3_date": "",
                "contact_3": "",
                "contact_3_title": "",
                "contact_3_phone": "",
            }
        )

    # Apply up to 3 best contacts per company, preferring PERM then LCA.
    if rows:
        for row in rows:
            norm = normalize_company_name(row["company_name"])
            contacts = (perm_contacts.get(norm) or []) + [
                c for c in (lca_contacts.get(norm) or []) if c not in (perm_contacts.get(norm) or [])
            ]
            contacts = contacts[:3]
            for i, contact in enumerate(contacts, start=1):
                row[f"contact_{i}"] = contact.get("name", "")
                row[f"contact_{i}_title"] = contact.get("title", "")
                row[f"contact_{i}_phone"] = contact.get("phone", "")
                row[f"email_{i}"] = contact.get("email", "")

    out_df = pd.DataFrame(
        rows,
        columns=[
            "company_tier",
            "company_name",
            "h1b",
            "h1b1_chile",
            "h1b1_singapore",
            "e3_australian",
            "green_card",
            "email_1",
            "email_1_date",
            "contact_1",
            "contact_1_title",
            "contact_1_phone",
            "email_2",
            "email_2_date",
            "contact_2",
            "contact_2_title",
            "contact_2_phone",
            "email_3",
            "email_3_date",
            "contact_3",
            "contact_3_title",
            "contact_3_phone",
        ],
    )

    if not out_df.empty:
        out_df = out_df.sort_values(
            ["h1b", "green_card", "h1b1_chile", "h1b1_singapore", "e3_australian"],
            ascending=False,
        )

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(output, index=False)

    quality_summary = _quality_summary(out_df)
    if strict_validation and not quality_summary["validation"]["passed"]:
        raise ValueError(
            "Pipeline validation failed: "
            + "; ".join(quality_summary["validation"]["errors"])
        )

    result = PipelineResult(
        output_path=str(output),
        rows_written=int(len(out_df)),
        lca_source=lca_path_or_url,
        perm_source=perm_path_or_url,
        lca_employer_col=lca_employer_col,
        lca_visa_col=lca_visa_col,
        perm_employer_col=perm_employer_col,
        discovered_from_performance_url=discovered_from_page,
        run_at_utc=datetime.now(UTC).isoformat(),
        manifest_path=manifest_path,
        quality_summary=quality_summary,
    )

    manifest = {
        "run_at_utc": result.run_at_utc,
        "output_path": result.output_path,
        "rows_written": result.rows_written,
        "lca_source": result.lca_source,
        "perm_source": result.perm_source,
        "lca_employer_col": result.lca_employer_col,
        "lca_visa_col": result.lca_visa_col,
        "perm_employer_col": result.perm_employer_col,
        "discovered_from_performance_url": result.discovered_from_performance_url,
        "quality_summary": result.quality_summary,
    }
    manifest_file = Path(manifest_path)
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return result
