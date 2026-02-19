# Internal DOL Pipeline

This pipeline pulls sponsorship source data from DOL and rebuilds the canonical company dataset used by MCP job matching.

## Flow
1. Discover latest LCA + PERM disclosure files from the DOL performance page.
2. Download disclosure files into local raw storage (`data/raw/dol/<timestamp>/`).
3. Build canonical CSV at `VISA_COMPANY_DATASET_PATH`.
4. Write run manifest to `data/pipeline/last_run.json`.

## Run methods
- Python entrypoint:
  - `visa-jobs-pipeline --output-path data/companies.csv`
- Shell wrapper:
  - `scripts/run_internal_pipeline.sh --output-path data/companies.csv`

## Optional overrides
- `--lca <path-or-url>`
- `--perm <path-or-url>`
- `--performance-url <url>`
- `--raw-dir <dir>`
- `--manifest <path>`
- `--no-strict-validation` (allow output even if validation checks fail)

## Validation
By default, pipeline runs are strict and fail on core quality issues:
- no rows produced
- duplicate normalized company names
- blank company names
- negative visa values
- zero aggregate visas

## Output schema
The generated CSV uses the canonical header row:
`company_tier,company_name,h1b,h1b1_chile,h1b1_singapore,e3_australian,green_card,email_1,email_1_date,contact_1,contact_1_title,contact_1_phone,email_2,email_2_date,contact_2,contact_2_title,contact_2_phone,email_3,email_3_date,contact_3,contact_3_title,contact_3_phone`
