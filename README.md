# Channel Partner Commission Engine

A production-grade, configuration-driven batch ETL system that automates commission payout calculations for loan channel partners (DSAs and Connectors) across multiple financial products.

Built to demonstrate real-world data engineering patterns used in **fintech commission processing** — slab-based calculations, sequence logic, statutory deductions, reconciliation, and audit-ready reporting.

---

## Table of Contents

- [Business Context](#business-context)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Features](#features)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Real-World Example](#real-world-example)
- [Sample Output](#sample-output)
- [Testing](#testing)
- [Design Decisions](#design-decisions)

---

## Business Context

In lending institutions, **channel partners** (Direct Selling Agents and Connectors) source loan business and earn commissions based on:

- **Product type** — Personal Loan, Home Loan, MSME, LAP, UBL, Cross-Sell
- **Disbursement amount** — slab-based rates (higher amounts = higher rates)
- **Loan sequence** — first loan from a partner earns full rate; subsequent loans may earn reduced rates
- **Partner category** — DSA vs Connector have different payout rules
- **Corporate status** — determines GST/TDS treatment

This engine automates what is typically a manual, error-prone monthly process involving multiple Excel sheets, reducing it to a single reproducible pipeline run.

---

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐     ┌──────────────┐
│  Warehouse  │────▶│  Extraction  │────▶│   Validation    │────▶│  Calculator  │
│  (DuckDB)   │     │              │     │  (6 rules)      │     │  (Slabs +    │
└─────────────┘     └──────────────┘     └─────────────────┘     │  Sequence)   │
                                                                  └──────┬───────┘
                                                                         │
                    ┌──────────────┐     ┌─────────────────┐             │
                    │   Contest    │◀────┤  Valid Records   │◀────────────┘
                    │   Module     │     └─────────────────┘
                    └──────┬───────┘                │
                           │                        ▼
                    ┌──────┴───────┐     ┌─────────────────┐     ┌──────────────┐
                    │   Reports    │◀────┤   Deductions    │────▶│Reconciliation│
                    │  (CSV)       │     │  (GST + TDS)    │     │              │
                    └──────┬───────┘     └─────────────────┘     └──────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │   Storage    │
                    │  (Local/S3)  │
                    └──────────────┘
```

**Pipeline Flow:**
1. **Extract** — Pull loans, disbursements, and partner data from the warehouse
2. **Validate** — Check for missing fields, referential integrity, invalid amounts
3. **Calculate** — Apply slab-based rates with sequence multipliers and tier adjustments
4. **Contest** — Evaluate monthly/quarterly incentive qualification
5. **Deductions** — Apply GST (18% corporate) and TDS (10% corporate / 5% non-corporate)
6. **Reconcile** — Compare against reference payouts, flag discrepancies
7. **Report** — Generate CSV files (payout, contest, reconciliation)
8. **Upload** — Push reports to configured storage backend

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Language | Python 3.11+ | Core implementation |
| Data Processing | pandas | DataFrame operations, transformations |
| Warehouse | DuckDB | Local OLAP database (swappable for Snowflake) |
| Configuration | PyYAML | Externalized business rules in YAML |
| Storage | Local FS / MinIO / S3 | Report upload (Protocol-based backend) |
| Testing | pytest | Unit and integration tests |
| Property Testing | Hypothesis | Formal correctness verification |
| Monetary Math | decimal.Decimal | Precise financial calculations (no floating-point) |

**Why these choices:**
- **DuckDB** over Postgres — zero-config OLAP database, simulates Snowflake locally with full SQL support
- **pandas** over PySpark — lightweight for local runs while keeping the same DataFrame semantics
- **Protocol-based DI** — backends are swappable without code changes (DuckDB → Snowflake, LocalFS → S3)
- **YAML configs** — business rules change monthly; externalizing them makes the engine data-driven

---

## Features

### Commission Calculation
- **6 loan products** — PL, HL, MSME, LAP, UBL, CSC (each with distinct slab rates)
- **PL Prime** — special sub-category with higher rates and different sequence tiers
- **Slab-based rates** — configurable ranges mapped to commission percentages
- **Disbursement sequence** — first disbursement at full rate, subsequent at 50%
- **Loan sequence tiers** — rate adjustments based on cumulative loans sourced by a partner

### Business Rules
- **Eligibility filtering** — minimum amounts, active partner checks, product-specific rules
- **Month allocation** — assign payouts to correct month using cheque handover or disbursement date
- **Cutoff date filtering** — process only disbursements within the cycle window
- **Partner classification** — DSA vs Connector, Corporate vs Non-Corporate

### Financial Processing
- **GST calculation** — 18% for corporate partners, 0% for non-corporate
- **TDS deduction** — 10% corporate, 5% non-corporate
- **Net payout formula** — Corporate: `net = gross + gst - tds` | Non-Corporate: `net = gross - tds`
- **Decimal precision** — all monetary values use `Decimal` with 2-place rounding

### Contest & Incentives
- **Monthly contests** — e.g., "10+ PL disbursements in a month = ₹5,000 bonus"
- **Quarterly contests** — e.g., "₹5Cr+ total disbursed = 0.05% of total as bonus"
- **Fixed and percentage payouts** — configurable per contest

### Data Quality
- **6-rule validation** — missing LAN, product, partner, date, invalid amount, unmatched partner
- **Reconciliation** — match against reference data, flag discrepancies with tolerance
- **Exception tracking** — every excluded record has a documented reason
- **Reproducibility** — identical inputs + config = byte-for-byte identical outputs

---

## Project Structure

```
channel-partner-commission-engine/
├── config/
│   ├── settings.yaml              # Warehouse, storage, processing settings
│   ├── slabs/
│   │   ├── personal_loan.yaml     # PL: 0.50% / 0.75% / 1.00% slabs
│   │   ├── home_loan.yaml         # HL: 0.30% / 0.40% / 0.50% slabs
│   │   ├── msme.yaml              # MSME: 0.60% / 0.80% / 1.00% slabs
│   │   ├── lap.yaml               # LAP: 0.40% / 0.55% / 0.70% slabs
│   │   ├── ubl.yaml               # UBL: 0.70% / 0.90% / 1.10% slabs
│   │   ├── cross_sell.yaml        # CSC: 0.80% / 1.00% / 1.20% slabs
│   │   └── pl_prime.yaml          # PL Prime: 0.60% / 0.90% / 1.20% slabs
│   ├── eligibility_rules.yaml     # Min amounts, active partner checks
│   ├── contests.yaml              # Monthly/quarterly incentive programs
│   └── deductions.yaml            # GST/TDS rates by corporate classification
├── src/commission_engine/
│   ├── engine.py                  # Pipeline orchestrator
│   ├── extractor.py               # Warehouse extraction (Protocol + DuckDB)
│   ├── validator.py               # Input validation (6 rules)
│   ├── calculator.py              # Slab lookup, sequence, eligibility
│   ├── contest.py                 # Contest evaluation
│   ├── deductions.py              # GST/TDS application
│   ├── reconciliation.py          # Payout matching
│   ├── reporter.py                # CSV generation
│   ├── uploader.py                # Storage upload (Protocol + LocalFS)
│   ├── config_loader.py           # YAML parsing and validation
│   ├── models.py                  # Result dataclasses
│   └── exceptions.py              # Custom exception hierarchy
├── tests/                         # 179 unit + integration tests
├── data/synthetic/
│   └── generate.py                # Synthetic data generator (seed=42)
├── output/                        # Generated reports land here
├── pyproject.toml                 # Project config + dependencies
└── README.md
```

---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/D-Haku/Channel-Partner-Commission-Engine.git
cd Channel-Partner-Commission-Engine
pip install -e ".[dev]"
```

### 2. Generate synthetic data

```bash
python data/synthetic/generate.py
```

Output:
```
Channel Partner Commission Engine - Synthetic Data Generator
============================================================
Random seed: 42

Generating partners...
  Partners: 500 (DSA: 297, Connector: 203, Corporate: 145, Active: 451)

Generating loans...
  Loans: 5000 (PL: 30%, HL: 20%, MSME: 15%, LAP: 15%, UBL: 10%, CSC: 10%)
  PL Prime: 152

Generating disbursements...
  Disbursements: 10835 (First: 5000, Subsequent: 5835)

Seeding DuckDB warehouse... Done!
```

### 3. Run the engine

```python
from datetime import date
from pathlib import Path
from commission_engine.engine import create_engine

engine = create_engine(Path("config"))
result = engine.run(cycle="2024-01", cutoff_date=date(2024, 1, 31))

print(f"Extracted: {result.record_counts['extracted_disbursements']} disbursements")
print(f"Valid: {result.record_counts['valid_disbursements']}")
print(f"Excluded: {result.record_counts['excluded_disbursements']}")
print(f"Eligible: {result.record_counts['eligible_commissions']}")
print(f"Contest qualifications: {result.record_counts['contest_qualifications']}")
print(f"Reports generated: {result.report_paths}")
```

### 4. Run tests

```bash
pytest                    # All 179 tests
pytest -v                 # Verbose output
pytest --cov              # With coverage report
```

---

## Configuration

### Slab Configuration (per product)

```yaml
# config/slabs/personal_loan.yaml
product: PL
slab_basis: disbursed_amount
slabs:
  - min: 0
    max: 500000
    rate_type: percentage
    rate: 0.50          # 0.50% for ₹0 - ₹5L
  - min: 500001
    max: 1500000
    rate_type: percentage
    rate: 0.75          # 0.75% for ₹5L - ₹15L
  - min: 1500001
    max: null           # unbounded upper
    rate_type: percentage
    rate: 1.00          # 1.00% for ₹15L+

sequence_rules:
  first_disbursement_multiplier: 1.0    # Full rate for first disbursement
  subsequent_disbursement_multiplier: 0.5  # Half rate for subsequent

loan_sequence_tiers:
  - sequence_min: 1
    sequence_max: 5
    rate_adjustment: 0.0    # No adjustment for first 5 loans
  - sequence_min: 6
    sequence_max: null
    rate_adjustment: -0.10  # -0.10% for 6th loan onwards
```

### Deduction Configuration

```yaml
# config/deductions.yaml
corporate:
  gst_rate: 0.18       # 18% GST
  tds_rate: 0.10       # 10% TDS
  formula: "net = gross + gst - tds"

non_corporate:
  gst_rate: 0.0        # No GST
  tds_rate: 0.05       # 5% TDS
  formula: "net = gross - tds"
```

---

## Real-World Example

### Scenario: January 2024 Payout Cycle

**Partner:** Alpha Corp (DSA, Corporate)  
**Loan:** Personal Loan, ₹8,00,000 disbursed on Jan 15, 2024  
**Details:** First disbursement, Partner's 3rd loan overall

**Calculation:**

```
1. Slab lookup: ₹8,00,000 falls in slab ₹5L–₹15L → rate = 0.75%
2. Sequence: First disbursement → multiplier = 1.0
3. Loan tier: 3rd loan (tier 1-5) → adjustment = 0.0
4. Final rate: 0.75 × 1.0 + 0.0 = 0.75%
5. Gross commission: ₹8,00,000 × 0.75 / 100 = ₹6,000.00

6. Corporate deductions:
   GST: ₹6,000 × 18% = ₹1,080.00
   TDS: ₹6,000 × 10% = ₹600.00
   Net: ₹6,000 + ₹1,080 - ₹600 = ₹6,480.00
```

**If the same partner had a subsequent disbursement (2nd tranche):**

```
1. Same slab: 0.75%
2. Subsequent disbursement → multiplier = 0.5
3. Final rate: 0.75 × 0.5 + 0.0 = 0.375%
4. Gross: ₹8,00,000 × 0.375 / 100 = ₹3,000.00
5. Net (corporate): ₹3,000 + ₹540 - ₹300 = ₹3,240.00
```

### Contest Example

**Monthly PL Volume Contest:**
- Rule: 10+ PL disbursements in a month
- Payout: ₹5,000 fixed bonus

If Alpha Corp sources 12 Personal Loans in January → qualifies → ₹5,000 bonus added to payout.

---

## Sample Output

### Payout Report (`payout_report.csv`)

```csv
LAN,Partner_ID,Loan_Product,Gross_Commission,GST_Amount,TDS_Amount,Net_Payout,Month_Allocation
LAN00142,P0023,PL,1250.00,225.00,125.00,1350.00,2024-01
LAN00289,P0045,HL,2100.00,0,105.00,1995.00,2024-01
LAN00512,P0112,MSME,4800.00,864.00,480.00,5184.00,2024-01
LAN00891,P0023,PL,625.00,112.50,62.50,675.00,2024-01
```

### Contest Report (`contest_report.csv`)

```csv
Partner_ID,Contest_ID,Payout
P0023,MONTHLY_PL_VOLUME,5000
P0112,QUARTERLY_REVENUE,2500000.0
P0045,MONTHLY_PL_VOLUME,0
```

### Reconciliation Report (`reconciliation_report.csv`)

```csv
LAN,Computed_Amount,Reference_Amount,Difference,Status
LAN00289,1995.00,2150.00,155.00,discrepancy
LAN00750,None,3200.00,3200.00,missing_computed
LAN01023,4500.00,None,4500.00,missing_reference
```

---

## Testing

### Test Coverage

```
179 tests across 10 test modules:
├── test_calculator.py      — 57 tests (slabs, sequence, eligibility, allocation, PL Prime, calculate)
├── test_config_loader.py   — 22 tests (YAML parsing, validation, error handling)
├── test_contest.py         — 16 tests (monthly, quarterly, multiple partners, edge cases)
├── test_deductions.py      — 13 tests (corporate, non-corporate, rounding, edge cases)
├── test_engine.py          — 12 tests (full pipeline, reconciliation, error propagation)
├── test_reconciliation.py  — 11 tests (matching, discrepancies, tolerance, count invariant)
├── test_reporter.py        — 14 tests (CSV format, headers, all report types)
├── test_uploader.py        — 11 tests (local FS upload, failure handling)
└── test_validator.py       — 23 tests (all 6 rules, priority ordering, edge cases)
```

### Run specific test groups

```bash
pytest tests/test_calculator.py     # Just calculator tests
pytest -k "test_corporate"          # Tests matching a keyword
pytest --tb=short -q                # Quick summary mode
```

---

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| `Decimal` for all money | Avoids floating-point errors (₹333.33 × 18% = ₹59.9994 → rounds correctly) |
| Protocol-based backends | Swap DuckDB → Snowflake or LocalFS → S3 without changing business logic |
| YAML configuration | Business rules change monthly; no code changes needed for rate updates |
| Row-level validation | Collect all errors, continue processing valid records (no fail-fast on data issues) |
| Fail-fast on infrastructure | Connection/config errors abort immediately (no partial results) |
| Fixed-seed synthetic data | `random.seed(42)` ensures reproducible test data across environments |
| Deterministic pipeline | Same input + config = identical CSV output (auditability requirement) |

---

## Extending

**Add a new loan product:**
1. Create `config/slabs/new_product.yaml` with slab definitions
2. The engine automatically picks it up on next run

**Switch to Snowflake:**
1. Update `config/settings.yaml`: `warehouse.backend: snowflake`
2. Set environment variables: `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_PASSWORD`
3. Implement `SnowflakeBackend` following the `WarehouseBackend` Protocol

**Add a new contest:**
1. Add entry to `config/contests.yaml` with qualification rules and payout definition
2. No code changes needed

---

## License

MIT
