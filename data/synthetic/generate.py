"""
Synthetic data generator for the Channel Partner Commission Engine.

Generates:
- 500+ partner records
- 5000+ loan records
- 10000+ disbursement records
- Reference payout data with intentional discrepancies

Seeds a DuckDB warehouse file at data/warehouse.duckdb.

Usage:
    python data/synthetic/generate.py
"""

import random
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pandas as pd

# Fixed seed for reproducibility
SEED = 42
random.seed(SEED)

# Output path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
WAREHOUSE_PATH = PROJECT_ROOT / "data" / "warehouse.duckdb"

# ─── Configuration Constants ───────────────────────────────────────────────────

NUM_PARTNERS = 500
NUM_LOANS = 5000
TARGET_DISBURSEMENTS = 10000

LOAN_PRODUCTS = ["PL", "HL", "MSME", "LAP", "UBL", "CSC"]
PRODUCT_DISTRIBUTION = {
    "PL": 0.30,
    "HL": 0.20,
    "MSME": 0.15,
    "LAP": 0.15,
    "UBL": 0.10,
    "CSC": 0.10,
}

# Sanctioned amount ranges per product (min, max)
AMOUNT_RANGES = {
    "PL": (50_000, 2_000_000),
    "HL": (500_000, 10_000_000),
    "MSME": (100_000, 5_000_000),
    "LAP": (200_000, 8_000_000),
    "UBL": (50_000, 2_000_000),
    "CSC": (30_000, 1_000_000),
}

# Date ranges
PARTNER_REG_START = date(2022, 1, 1)
PARTNER_REG_END = date(2024, 6, 30)
LOAN_APP_START = date(2023, 7, 1)
LOAN_APP_END = date(2025, 3, 31)

# PL Prime probability (~10% of PL loans)
PL_PRIME_RATE = 0.10


# ─── Helper Functions ──────────────────────────────────────────────────────────


def random_date(start: date, end: date) -> date:
    """Generate a random date between start and end (inclusive)."""
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


def generate_partner_name(index: int, partner_type: str) -> str:
    """Generate a plausible partner name."""
    dsa_names = [
        "Capital Finance", "Prime Loans", "Star Associates", "Golden Bridge",
        "Trust Financial", "Metro Lending", "Swift Capital", "Royal Finance",
        "Zenith Partners", "Eagle Advisors", "Apex Financial", "Lotus Group",
        "Diamond Brokers", "Silver Line", "Crystal Finance", "Pioneer Loans",
        "Summit Partners", "Atlas Finance", "Venture Loans", "Pacific Credit",
    ]
    connector_names = [
        "Sharma Associates", "Patel Enterprises", "Kumar Financial",
        "Singh Advisors", "Gupta Services", "Mehta Group", "Joshi Consultants",
        "Verma Partners", "Reddy Finance", "Nair Associates", "Das Services",
        "Agarwal Group", "Bhatia Enterprises", "Kapoor Advisors", "Mishra Finance",
        "Rao Consultants", "Pillai Associates", "Iyer Services", "Banerjee Group",
        "Mukherjee Partners",
    ]
    names = dsa_names if partner_type == "DSA" else connector_names
    base_name = names[index % len(names)]
    suffix = f" {index // len(names) + 1}" if index >= len(names) else ""
    return f"{base_name}{suffix}"


# ─── Data Generation ───────────────────────────────────────────────────────────


def generate_partners() -> pd.DataFrame:
    """Generate 500+ partner records."""
    partners = []
    for i in range(NUM_PARTNERS):
        partner_id = f"P{i + 1:04d}"

        # 60% DSA, 40% Connector
        partner_type = "DSA" if random.random() < 0.60 else "Connector"

        # 30% Corporate, 70% Non-Corporate
        corporate_flag = random.random() < 0.30

        # ~90% active, ~10% inactive
        active = random.random() < 0.90

        registration_date = random_date(PARTNER_REG_START, PARTNER_REG_END)
        partner_name = generate_partner_name(i, partner_type)

        partners.append({
            "partner_id": partner_id,
            "partner_name": partner_name,
            "partner_type": partner_type,
            "corporate_flag": corporate_flag,
            "registration_date": registration_date,
            "active": active,
        })

    return pd.DataFrame(partners)


def generate_loans(partners_df: pd.DataFrame) -> pd.DataFrame:
    """Generate 5000+ loan records across all products."""
    active_partners = partners_df[partners_df["active"]]["partner_id"].tolist()
    all_partners = partners_df["partner_id"].tolist()

    loans = []
    for i in range(NUM_LOANS):
        lan = f"LAN{i + 1:05d}"

        # Determine product based on distribution
        rand_val = random.random()
        cumulative = 0.0
        loan_product = "PL"  # default
        for product, prob in PRODUCT_DISTRIBUTION.items():
            cumulative += prob
            if rand_val <= cumulative:
                loan_product = product
                break

        # ~10% of PL loans are PL Prime
        is_pl_prime = loan_product == "PL" and random.random() < PL_PRIME_RATE

        # Sanctioned amount within product range
        amt_min, amt_max = AMOUNT_RANGES[loan_product]
        sanctioned_amount = round(random.uniform(amt_min, amt_max), 2)

        # Application date
        application_date = random_date(LOAN_APP_START, LOAN_APP_END)

        # Assign partner (90% from active, 10% from all including inactive)
        if random.random() < 0.90:
            partner_id = random.choice(active_partners)
        else:
            partner_id = random.choice(all_partners)

        loans.append({
            "lan": lan,
            "partner_id": partner_id,
            "loan_product": loan_product,
            "is_pl_prime": is_pl_prime,
            "sanctioned_amount": sanctioned_amount,
            "application_date": application_date,
        })

    return pd.DataFrame(loans)


def generate_disbursements(loans_df: pd.DataFrame) -> pd.DataFrame:
    """Generate 10000+ disbursement records (1-3 per loan)."""
    disbursements = []
    disb_id_counter = 0

    for _, loan in loans_df.iterrows():
        # Determine number of disbursements (1-3)
        # Weight to ensure >10000 total from 5000 loans (average ~2.1)
        num_disb = random.choices([1, 2, 3], weights=[20, 45, 35])[0]

        for seq in range(1, num_disb + 1):
            disb_id_counter += 1
            disbursement_id = f"D{disb_id_counter:05d}"

            # Disbursed amount
            if seq == 1:
                # First disbursement: 50-100% of sanctioned
                pct = random.uniform(0.50, 1.00)
            else:
                # Subsequent: 10-50% of sanctioned
                pct = random.uniform(0.10, 0.50)
            disbursed_amount = round(float(loan["sanctioned_amount"]) * pct, 2)

            # Disbursement date: application_date + random days
            app_date = loan["application_date"]
            if seq == 1:
                days_offset = random.randint(10, 60)
            else:
                days_offset = random.randint(30, 120) + (seq - 1) * 30
            disbursement_date = app_date + timedelta(days=days_offset)

            # Cheque handover date: disbursement_date + 0-5 days, 20% null
            if random.random() < 0.20:
                cheque_handover_date = None
            else:
                cheque_handover_date = disbursement_date + timedelta(
                    days=random.randint(0, 5)
                )

            disbursements.append({
                "disbursement_id": disbursement_id,
                "lan": loan["lan"],
                "partner_id": loan["partner_id"],
                "loan_product": loan["loan_product"],
                "disbursed_amount": disbursed_amount,
                "disbursement_date": disbursement_date,
                "cheque_handover_date": cheque_handover_date,
                "disbursement_sequence": seq,
            })

    return pd.DataFrame(disbursements)


def generate_reference_payouts(loans_df: pd.DataFrame) -> pd.DataFrame:
    """
    Generate reference payout data with intentional discrepancies.

    - 80% of loans: reference_amount = a plausible computed value (simulated)
    - 10% of loans: reference_amount differs by 50-500 (discrepancies)
    - 10% of loans: missing from reference (to test missing_computed scenario)
    """
    # Simple commission simulation for reference values
    # Use a flat 0.75% rate as a baseline "correct" computation
    BASE_RATE = 0.0075

    reference_records = []
    loan_list = loans_df.to_dict("records")

    # Shuffle to make the selection random but deterministic
    shuffled_indices = list(range(len(loan_list)))
    random.shuffle(shuffled_indices)

    # Split: 80% correct, 10% discrepancy, 10% missing
    n_correct = int(len(loan_list) * 0.80)
    n_discrepancy = int(len(loan_list) * 0.10)
    # Remaining 10% are simply excluded (missing from reference)

    correct_indices = shuffled_indices[:n_correct]
    discrepancy_indices = shuffled_indices[n_correct:n_correct + n_discrepancy]

    for idx in correct_indices:
        loan = loan_list[idx]
        # Simulate a "correct" reference amount with small tolerance noise
        base_amount = float(loan["sanctioned_amount"]) * BASE_RATE
        # Add tiny noise within tolerance (±0.005)
        noise = random.uniform(-0.005, 0.005)
        reference_amount = round(base_amount + noise, 2)
        reference_records.append({
            "lan": loan["lan"],
            "reference_amount": reference_amount,
        })

    for idx in discrepancy_indices:
        loan = loan_list[idx]
        base_amount = float(loan["sanctioned_amount"]) * BASE_RATE
        # Introduce discrepancy of 50-500
        discrepancy = random.uniform(50, 500) * random.choice([-1, 1])
        reference_amount = round(base_amount + discrepancy, 2)
        reference_records.append({
            "lan": loan["lan"],
            "reference_amount": reference_amount,
        })

    return pd.DataFrame(reference_records)


# ─── DuckDB Seeding ────────────────────────────────────────────────────────────


def seed_duckdb(
    partners_df: pd.DataFrame,
    loans_df: pd.DataFrame,
    disbursements_df: pd.DataFrame,
    reference_payouts_df: pd.DataFrame,
) -> None:
    """Create/overwrite DuckDB warehouse and insert all generated data."""
    # Remove existing database file if present
    if WAREHOUSE_PATH.exists():
        WAREHOUSE_PATH.unlink()

    # Ensure parent directory exists
    WAREHOUSE_PATH.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(WAREHOUSE_PATH))

    try:
        # Create partners table
        con.execute("""
            CREATE TABLE partners (
                partner_id VARCHAR PRIMARY KEY,
                partner_name VARCHAR,
                partner_type VARCHAR,
                corporate_flag BOOLEAN,
                registration_date DATE,
                active BOOLEAN
            )
        """)

        # Create loans table
        con.execute("""
            CREATE TABLE loans (
                lan VARCHAR PRIMARY KEY,
                partner_id VARCHAR,
                loan_product VARCHAR,
                is_pl_prime BOOLEAN,
                sanctioned_amount DECIMAL(15, 2),
                application_date DATE
            )
        """)

        # Create disbursements table
        con.execute("""
            CREATE TABLE disbursements (
                disbursement_id VARCHAR PRIMARY KEY,
                lan VARCHAR,
                partner_id VARCHAR,
                loan_product VARCHAR,
                disbursed_amount DECIMAL(15, 2),
                disbursement_date DATE,
                cheque_handover_date DATE,
                disbursement_sequence INTEGER
            )
        """)

        # Create reference_payouts table
        con.execute("""
            CREATE TABLE reference_payouts (
                lan VARCHAR PRIMARY KEY,
                reference_amount DECIMAL(15, 2)
            )
        """)

        # Insert data using pandas DataFrames
        con.execute("INSERT INTO partners SELECT * FROM partners_df")
        con.execute("INSERT INTO loans SELECT * FROM loans_df")
        con.execute("INSERT INTO disbursements SELECT * FROM disbursements_df")
        con.execute(
            "INSERT INTO reference_payouts SELECT * FROM reference_payouts_df"
        )

        con.commit()
    finally:
        con.close()


# ─── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    """Generate all synthetic data and seed the DuckDB warehouse."""
    print("=" * 60)
    print("Channel Partner Commission Engine - Synthetic Data Generator")
    print("=" * 60)
    print(f"\nRandom seed: {SEED}")
    print(f"Output: {WAREHOUSE_PATH}\n")

    # Generate partners
    print("Generating partners...")
    partners_df = generate_partners()
    print(f"  Partners: {len(partners_df)}")
    print(f"    DSA: {(partners_df['partner_type'] == 'DSA').sum()}")
    print(f"    Connector: {(partners_df['partner_type'] == 'Connector').sum()}")
    print(f"    Corporate: {partners_df['corporate_flag'].sum()}")
    print(f"    Non-Corporate: {(~partners_df['corporate_flag']).sum()}")
    print(f"    Active: {partners_df['active'].sum()}")
    print(f"    Inactive: {(~partners_df['active']).sum()}")

    # Generate loans
    print("\nGenerating loans...")
    loans_df = generate_loans(partners_df)
    print(f"  Loans: {len(loans_df)}")
    for product in LOAN_PRODUCTS:
        count = (loans_df["loan_product"] == product).sum()
        pct = count / len(loans_df) * 100
        print(f"    {product}: {count} ({pct:.1f}%)")
    pl_prime_count = loans_df["is_pl_prime"].sum()
    print(f"    PL Prime: {pl_prime_count}")

    # Generate disbursements
    print("\nGenerating disbursements...")
    disbursements_df = generate_disbursements(loans_df)
    print(f"  Disbursements: {len(disbursements_df)}")
    first_disb = (disbursements_df["disbursement_sequence"] == 1).sum()
    subsequent_disb = (disbursements_df["disbursement_sequence"] > 1).sum()
    print(f"    First disbursements: {first_disb}")
    print(f"    Subsequent disbursements: {subsequent_disb}")
    null_cheque = disbursements_df["cheque_handover_date"].isna().sum()
    print(f"    Null cheque_handover_date: {null_cheque}")

    # Generate reference payouts
    print("\nGenerating reference payouts...")
    reference_payouts_df = generate_reference_payouts(loans_df)
    print(f"  Reference payouts: {len(reference_payouts_df)}")
    print(f"    Correct (~80%): {int(len(loans_df) * 0.80)}")
    print(f"    Discrepancies (~10%): {int(len(loans_df) * 0.10)}")
    print(f"    Missing from reference (~10%): "
          f"{len(loans_df) - len(reference_payouts_df)}")

    # Seed DuckDB
    print("\nSeeding DuckDB warehouse...")
    seed_duckdb(partners_df, loans_df, disbursements_df, reference_payouts_df)
    print(f"  Database created: {WAREHOUSE_PATH}")

    # Verify
    con = duckdb.connect(str(WAREHOUSE_PATH), read_only=True)
    try:
        print("\nVerification:")
        for table in ["partners", "loans", "disbursements", "reference_payouts"]:
            count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  {table}: {count} rows")
    finally:
        con.close()

    print("\n" + "=" * 60)
    print("Data generation complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
