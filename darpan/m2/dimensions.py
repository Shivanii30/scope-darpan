"""M2 canonical dimensions used to reconcile M1 raw labels."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DimensionRow:
    id: str
    label: str
    kind: str
    aliases: tuple[str, ...] = ()


BANKS = (
    DimensionRow("sbi", "State Bank of India", "PSU", ("SBI", "STATE BANK OF INDIA", "SBI & ASSOCIATES", "SBI & ASSOCIATES BANKS")),
    DimensionRow("nationalized_banks", "Nationalized Banks", "PSU", ("NATIONALIZED BANKS", "PUBLIC SECTOR BANKS", "PUBLIC SECTOR BANKING")),
    DimensionRow("private_sector_banks", "Private Sector Banks", "PRIVATE", ("PRIVATE SECTOR BANKS", "PRIVATE BANKS")),
    DimensionRow("foreign_banks", "Foreign Banks", "FOREIGN", ("FOREIGN BANKS",)),
    DimensionRow("rrb_urban_coop_banks", "RRBs / Scheduled Primary Urban Co-op. Banks", "COOPERATIVE", ("RRB/URBAN CO-OP. BANKS", "RRBS/ SCHEDULED PRIMARY URBAN CO-OP. BANKS", "RRBs", "URBAN CO-OP. BANKS")),
    DimensionRow("payments_small_finance_banks", "Payments and Small Finance Banks", "SMALL_FINANCE", ("PAYMENTS AND SMALL FINANCE BANKS", "PAYMENTS BANKS", "SMALL FINANCE BANKS")),
    DimensionRow("nbfc", "NBFC", "NBFC", ("NBFCS", "NON-BANKING FINANCIAL COMPANIES", "NBFC")),
    DimensionRow("others", "Others", "UNKNOWN", ("OTHERS",)),
)

CATEGORIES = (
    DimensionRow("1", "ATM / Debit Cards", "category", ("ATM/DEBIT CARDS", "ATM / DEBIT CARDS", "ATM/ DEBIT CARDS", "ATM - DEBIT CARD")),
    DimensionRow("2", "Credit Cards", "category", ("CREDIT CARDS", "CREDIT CARD")),
    DimensionRow("3", "Loans", "category", ("LOANS", "LOAN ACCOUNT")),
    DimensionRow("4", "Deposits", "category", ("DEPOSITS", "DEPOSIT")),
    DimensionRow("5", "Mobile / Electronic Banking", "category", ("MOBILE/ELECTRONIC BANKING", "MOBILE / ELECTRONIC BANKING", "INTERNET BANKING", "UPI", "WALLET")),
    DimensionRow("6", "Non-observance of Fair Practice Code", "category", ("NON-OBSERVANCE OF FAIR PRACTICE CODE", "FAIR PRACTICE CODE", "FAIR PRACTICES")),
    DimensionRow("7", "Failure to Meet Commitments", "category", ("FAILURE TO MEET COMMITMENTS", "FAILURE ON THE BANK'S COMMITMENT")),
    DimensionRow("8", "DSA / Mis-selling", "category", ("DSA", "MIS-SELLING", "DIRECT SALES AGENT")),
    DimensionRow("9", "Charges / Levy", "category", ("LEVY OF", "LEVY OF CHARGES", "CHARGES")),
    DimensionRow("10", "Pension / Government Business", "category", ("PENSION", "GOVERNMENT BUSINESS")),
)

REGIONS = (
    DimensionRow("ahmedabad", "Ahmedabad", "region", ("AHMEDABAD",)),
    DimensionRow("bengaluru", "Bengaluru", "region", ("BENGALURU", "BANGALORE")),
    DimensionRow("bhopal", "Bhopal", "region", ("BHOPAL",)),
    DimensionRow("bhubaneswar", "Bhubaneswar", "region", ("BHUBANESWAR",)),
    DimensionRow("chandigarh", "Chandigarh", "region", ("CHANDIGARH",)),
    DimensionRow("chennai", "Chennai", "region", ("CHENNAI",)),
    DimensionRow("guwahati", "Guwahati", "region", ("GUWAHATI",)),
    DimensionRow("jaipur", "Jaipur", "region", ("JAIPUR",)),
    DimensionRow("kanpur", "Kanpur", "region", ("KANPUR",)),
    DimensionRow("kolkata", "Kolkata", "region", ("KOLKATA",)),
    DimensionRow("lucknow", "Lucknow", "region", ("LUCKNOW",)),
    DimensionRow("mumbai", "Mumbai", "region", ("MUMBAI",)),
    DimensionRow("new_delhi", "New Delhi", "region", ("NEW DELHI", "DELHI")),
    DimensionRow("patna", "Patna", "region", ("PATNA",)),
    DimensionRow("thiruvananthapuram", "Thiruvananthapuram", "region", ("THIRUVANANTHAPURAM", "TRIVANDRUM")),
)


def normalize_label(value: str) -> str:
    import re
    return re.sub(r"[^A-Z0-9]+", " ", (value or "").upper()).strip()


def match_dimension(label: str, rows: tuple[DimensionRow, ...]) -> DimensionRow | None:
    """Exact normalized or alias match only. No fuzzy guessing in M2."""
    norm = normalize_label(label)
    for row in rows:
        candidates = (row.label,) + row.aliases
        if norm in {normalize_label(c) for c in candidates}:
            return row
    return None
