from __future__ import annotations

from .base_runtime import *  # noqa: F401,F403
from .base_jobs import *  # noqa: F401,F403
from .base_state import *  # noqa: F401,F403

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


def _dedupe_raw_jobs(raw_jobs: pd.DataFrame | None) -> pd.DataFrame:
    if raw_jobs is None or raw_jobs.empty:
        return pd.DataFrame([])

    cdf = raw_jobs.copy()
    if "job_url" in cdf.columns:
        cdf["__dedupe_key"] = cdf["job_url"].fillna("").astype(str).str.strip()
    else:
        cdf["__dedupe_key"] = ""

    fallback_mask = cdf["__dedupe_key"] == ""
    if fallback_mask.any():
        for col in ("title", "company", "location", "site"):
            if col not in cdf.columns:
                cdf[col] = ""
        cdf.loc[fallback_mask, "__dedupe_key"] = (
            cdf.loc[fallback_mask, ["title", "company", "location", "site"]]
            .fillna("")
            .astype(str)
            .agg("|".join, axis=1)
        )

    cdf = cdf.drop_duplicates(subset=["__dedupe_key"], keep="first").drop(columns=["__dedupe_key"])
    return cdf.reset_index(drop=True)


def _find_related_titles_internal(job_title: str, limit: int = 8) -> list[str]:
    base = job_title.strip()
    if not base:
        return []
    normalized = base.lower()
    related: list[str] = []

    for key, values in RELATED_TITLE_HINTS.items():
        if key in normalized or normalized in key:
            related.extend(values)
            break

    if not related:
        if "engineer" in normalized:
            related.extend(
                [
                    base.replace("Engineer", "Developer"),
                    base.replace("Engineer", "Platform Engineer"),
                    base.replace("Engineer", "Systems Engineer"),
                ]
            )
        elif "developer" in normalized:
            related.extend(
                [
                    base.replace("Developer", "Engineer"),
                    base.replace("Developer", "Application Engineer"),
                    base.replace("Developer", "Software Engineer"),
                ]
            )
        elif "architect" in normalized:
            related.extend(
                [
                    base.replace("architect", "engineer").replace("Architect", "Engineer"),
                    f"Senior {base}",
                    f"Lead {base}",
                ]
            )

    if not related:
        related.extend(
            [
                f"Senior {base}",
                f"Lead {base}",
                f"{base} Specialist",
            ]
        )

    candidates = [c.strip() for c in related if c and c.strip()]
    deduped: list[str] = []
    seen: set[str] = {normalized}
    for item in candidates:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= max(1, limit):
            break
    return deduped


def _build_recovery_suggestions(
    *,
    location: str,
    job_title: str,
    hours_old: int,
    max_scan_results: int,
    accepted_jobs: int,
    returned_jobs: int,
    scan_exhausted: bool,
) -> list[dict[str, Any]]:
    low_yield = returned_jobs == 0 or (accepted_jobs < 10 and scan_exhausted)
    if not low_yield:
        return []

    related_titles = _find_related_titles_internal(job_title, limit=8)
    next_hours_old = min(max(hours_old * 2, hours_old + 168), 24 * 60)
    next_scan_cap = min(max(max_scan_results * 2, max_scan_results + 400), 5000)
    suggestions = [
        {
            "id": "expand_time_window",
            "description": "Broaden the posting time window to find older eligible roles.",
            "proposed_call_args": {"hours_old": int(next_hours_old)},
            "requires_user_confirmation": True,
        },
        {
            "id": "increase_scan_depth",
            "description": "Increase scan depth so the MCP can sift more postings before filtering.",
            "proposed_call_args": {"max_scan_results": int(next_scan_cap)},
            "requires_user_confirmation": True,
        },
    ]

    if related_titles:
        suggestions.insert(
            0,
            {
                "id": "related_titles",
                "description": "Try adjacent job titles that map to similar skill requirements.",
                "options": related_titles,
                "requires_user_confirmation": True,
            },
        )

    if "," in location:
        city = location.split(",", 1)[0].strip()
        suggestions.append(
            {
                "id": "nearby_location",
                "description": "Try a nearby metro location to widen supply.",
                "options": [city, f"{city} Metro Area", location],
                "requires_user_confirmation": True,
            }
        )

    return suggestions


def _evaluate_scraped_jobs(
    raw_jobs: pd.DataFrame,
    sponsor_df: pd.DataFrame,
    desired_visa_types: list[str],
    require_description_signal: bool,
    strictness_mode: str,
) -> list[EvaluatedJob]:
    results: list[EvaluatedJob] = []
    desired_visa_set = set(desired_visa_types)

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
        company_matches_requested_visa = False
        matched_company = False
        contacts: list[dict[str, str]] = []
        if normalized and normalized in sponsor_df.index:
            company_row = sponsor_df.loc[normalized]
            sponsor_stats = _company_stats(company_row)
            visa_counts = _visa_counts_from_company_row(company_row)
            visas_sponsored = [
                VISA_TYPE_LABELS[k]
                for k in ("h1b", "h1b1_chile", "h1b1_singapore", "e3_australian", "green_card")
                if visa_counts.get(k, 0) > 0
            ]
            matched_company = sponsor_stats.total_visas > 0
            contacts = _company_contacts(company_row) if matched_company else []
            if desired_visa_set:
                company_matches_requested_visa = any(visa_counts.get(v, 0) > 0 for v in desired_visa_set)

        rejected_for_negative = has_negative
        desc_visa_types = _visa_types_from_description(description)
        desc_matches_requested_visa = bool(desired_visa_set and desc_visa_types.intersection(desired_visa_set))
        desc_specific_mismatch = bool(
            desired_visa_set
            and desc_visa_types
            and not desc_visa_types.intersection(desired_visa_set)
        )
        desc_generic_sponsorship = bool(has_positive and not desc_visa_types)

        if desired_visa_set:
            if strictness_mode == "strict":
                matches_user_visa_preferences = (
                    company_matches_requested_visa
                    or desc_matches_requested_visa
                )
            else:
                matches_user_visa_preferences = (
                    company_matches_requested_visa
                    or desc_matches_requested_visa
                    or desc_generic_sponsorship
                )
                if desc_specific_mismatch and not company_matches_requested_visa:
                    matches_user_visa_preferences = False

        accept = False
        if not rejected_for_negative:
            if require_description_signal:
                accept = has_positive
            else:
                accept = matched_company or has_positive
            # Always enforce user visa fit so we never return "random sponsorship" jobs.
            if desired_visa_set:
                accept = accept and matches_user_visa_preferences
            # If a specific but different visa is listed, keep strict behavior unless company history proves fit.
            if desc_specific_mismatch and not company_matches_requested_visa:
                accept = False

        if not accept:
            continue

        matched_preference_labels = [
            VISA_TYPE_LABELS[v]
                for v in desired_visa_types
                if visa_counts.get(v, 0) > 0 or v in desc_visa_types
        ]
        eligibility_reasons: list[str] = []
        if strictness_mode == "strict":
            eligibility_reasons.append("Strict visa match mode is active.")
        else:
            eligibility_reasons.append("Balanced visa match mode is active.")
        if matched_company:
            company_visa_summary = ", ".join(
                [
                    f"{VISA_TYPE_LABELS[k]}={visa_counts.get(k, 0)}"
                    for k in ("h1b", "h1b1_chile", "h1b1_singapore", "e3_australian", "green_card")
                    if visa_counts.get(k, 0) > 0
                ]
            )
            if company_visa_summary:
                eligibility_reasons.append(
                    f"Company has historical sponsor filings ({company_visa_summary})."
                )
            else:
                eligibility_reasons.append("Company matched in sponsorship dataset.")
        if has_positive:
            eligibility_reasons.append("Job description mentions visa sponsorship language.")
        if matched_preference_labels:
            eligibility_reasons.append(
                f"Matches requested visa type(s): {', '.join(sorted(set(matched_preference_labels)))}."
            )
        elif strictness_mode == "balanced" and desc_generic_sponsorship:
            eligibility_reasons.append(
                "Accepted in balanced mode using generic sponsorship language."
            )

        contactability_score = 0.0
        if contacts:
            primary_contact = contacts[0]
            if str(primary_contact.get("email", "")).strip():
                contactability_score += 0.6
            if str(primary_contact.get("phone", "")).strip():
                contactability_score += 0.25
            if str(primary_contact.get("name", "")).strip():
                contactability_score += 0.1
            if str(primary_contact.get("title", "")).strip():
                contactability_score += 0.05
        contactability_score = min(1.0, round(contactability_score, 2))

        confidence_score = 0.0
        if matched_company:
            confidence_score += 0.65
        if has_positive:
            confidence_score += 0.20
        if matches_user_visa_preferences:
            confidence_score += 0.10
        if contactability_score > 0:
            confidence_score += 0.05
        confidence_score = min(1.0, round(confidence_score, 2))

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
                employer_contacts=contacts,
                visa_counts=visa_counts,
                visas_sponsored=visas_sponsored,
                matches_user_visa_preferences=matches_user_visa_preferences,
                eligibility_reasons=eligibility_reasons,
                confidence_score=confidence_score,
                confidence_model_version=CONFIDENCE_MODEL_VERSION,
                contactability_score=contactability_score,
                sponsor_stats=asdict(sponsor_stats) if sponsor_stats else None,
            )
        )

    # Rank by sponsorship confidence first, then contactability to prioritize outreach-friendly roles.
    return sorted(
        results,
        key=lambda job: (job.confidence_score, job.contactability_score),
        reverse=True,
    )


