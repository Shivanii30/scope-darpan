from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

REQUIRED_COMPLAINT_COLUMNS = {"bank_id", "year", "received"}

OPTIONAL_COMPLAINT_COLUMNS = {"region_id", "category_id", "sub_type", "disposed", "awards_issued","avg_resolution_days", "maintainable",}

@dataclass
class RawData:
    banks: pd.DataFrame
    regions: pd.DataFrame
    complaint_categories: pd.DataFrame
    complaints_annual: pd.DataFrame

def load_data(engine)->RawData:
    banks = pd.read_sql("SELECT * FROM banks", engine)
    regions = pd.read_sql("SELECT * FROM regions", engine)
    complaint_categories = pd.read_sql("SELECT * FROM complaint_categories", engine)
    complaints_annual = pd.read_sql("SELECT * FROM complaints_annual", engine)

    _validate_complaints(complaints_annual)
    return RawData(
        banks=banks,
        regions=regions,
        complaint_categories=complaint_categories,
        complaints_annual=complaints_annual,
    )

def _validate_complaints(df:pd.DataFrame)-> None:
    missing = REQUIRED_COMPLAINT_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns in complaints_annual: {missing}"
                        "Check load_to_db.py to ensure the complaints_annual table is created correctly.")
    
#for testing purposes
def main():
    from sqlalchemy import create_engine

    # Change this DSN if required
    engine = create_engine(
        "postgresql://postgres:password1@localhost:5432/ombudsman"
    )

    data = load_data(engine)

    print("\n=== BANKS ===")
    print(data.banks.head())
    print(f"Rows: {len(data.banks)}")

    print("\n=== REGIONS ===")
    print(data.regions.head())
    print(f"Rows: {len(data.regions)}")

    print("\n=== COMPLAINT CATEGORIES ===")
    print(data.complaint_categories.head())
    print(f"Rows: {len(data.complaint_categories)}")

    print("\n=== COMPLAINTS ANNUAL ===")
    print(data.complaints_annual.head())
    print(f"Rows: {len(data.complaints_annual)}")

    print("\nRequired column validation passed.")


if __name__ == "__main__":
    main()
