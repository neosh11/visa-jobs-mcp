from __future__ import annotations

import argparse
import json
import os

DEFAULT_OUTPUT_PATH = os.getenv("VISA_COMPANY_DATASET_PATH", "data/companies.csv")
DEFAULT_DOL_PERFORMANCE_URL = os.getenv(
    "VISA_DOL_PERFORMANCE_URL",
    "https://www.dol.gov/agencies/eta/foreign-labor/performance",
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run internal DOL data pipeline")
    parser.add_argument(
        "--output-path",
        default=DEFAULT_OUTPUT_PATH,
    )
    parser.add_argument("--lca", default="", help="LCA disclosure file path or URL")
    parser.add_argument("--perm", default="", help="PERM disclosure file path or URL")
    parser.add_argument(
        "--performance-url",
        default=DEFAULT_DOL_PERFORMANCE_URL,
        help="DOL performance page URL for discovery",
    )
    parser.add_argument(
        "--raw-dir",
        default=os.getenv("VISA_DOL_RAW_DIR", "data/raw/dol"),
        help="Directory to store downloaded source files",
    )
    parser.add_argument(
        "--manifest",
        default=os.getenv("VISA_DOL_MANIFEST_PATH", "data/pipeline/last_run.json"),
        help="Pipeline manifest output path",
    )
    parser.add_argument(
        "--no-strict-validation",
        action="store_true",
        help="Do not fail when validation checks find data quality errors",
    )
    args = parser.parse_args()

    from .pipeline import run_dol_pipeline

    result = run_dol_pipeline(
        output_path=args.output_path,
        lca_path_or_url=args.lca,
        perm_path_or_url=args.perm,
        performance_url=args.performance_url,
        raw_dir=args.raw_dir,
        manifest_path=args.manifest,
        strict_validation=not args.no_strict_validation,
    )

    print(
        json.dumps(
            {
                "output_path": result.output_path,
                "rows_written": result.rows_written,
                "lca_source": result.lca_source,
                "perm_source": result.perm_source,
                "manifest_path": result.manifest_path,
                "run_at_utc": result.run_at_utc,
                "validation_passed": result.quality_summary["validation"]["passed"],
                "validation_errors": result.quality_summary["validation"]["errors"],
                "validation_warnings": result.quality_summary["validation"]["warnings"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
