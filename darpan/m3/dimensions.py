"""M3 seed data for the dimension tables."""
from __future__ import annotations


BANKS = (
    ("sbi", "State Bank of India", "PSU", "SBI", "SBI & Associates; State Bank of India"),
    ("nationalized_banks", "Nationalized Banks", "PSU", None, "Public Sector Banks; Nationalized Banks"),
    ("private_sector_banks", "Private Sector Banks", "PRIVATE", None, "Private Banks; Private Sector Banks"),
    ("foreign_banks", "Foreign Banks", "FOREIGN", None, "Foreign Banks"),
    ("rrb_urban_coop_banks", "RRBs / Scheduled Primary Urban Co-op. Banks", "COOPERATIVE", None, "RRBs; Urban Co-op. Banks"),
    ("payments_small_finance_banks", "Payments and Small Finance Banks", "SMALL_FINANCE", None, "Payments Banks; Small Finance Banks"),
    ("nbfc", "NBFC", "NBFC", None, "NBFC; Non-Banking Financial Companies"),
    ("others", "Others", "UNKNOWN", None, "Others"),
)

CATEGORIES = (
    ("1", "ATM_DENIED", "ATM / Debit Cards", "ATM/ Debit Cards"),
    ("2", "CARD_FRAUD", "Credit Cards", "Credit Cards"),
    ("3", "LOAN", "Loans", "Loans"),
    ("4", "DEPOSIT", "Deposits", "Deposits"),
    ("5", "DIGITAL_BANKING", "Mobile / Electronic Banking", "Mobile/Electronic Banking"),
    ("6", "FAIR_PRACTICE", "Non-observance of Fair Practice Code", "Fair Practice Code"),
    ("7", "COMMITMENT", "Failure to Meet Commitments", "Failure to Meet Commitments"),
    ("8", "DSA_MISSELLING", "DSA / Mis-selling", "DSA; Mis-selling"),
    ("9", "CHARGES", "Charges / Levy", "Levy of Charges"),
    ("10", "PENSION_GOVERNMENT", "Pension / Government Business", "Pension; Government Business"),
)

REGIONS = (
    ("ahmedabad", "Ahmedabad", "Gujarat", None),
    ("bengaluru", "Bengaluru", "Karnataka", None),
    ("bhopal", "Bhopal", "Madhya Pradesh", None),
    ("bhubaneswar", "Bhubaneswar", "Odisha", None),
    ("chandigarh", "Chandigarh", "Chandigarh", None),
    ("chennai", "Chennai", "Tamil Nadu", None),
    ("guwahati", "Guwahati", "Assam", None),
    ("jaipur", "Jaipur", "Rajasthan", None),
    ("kanpur", "Kanpur", "Uttar Pradesh", None),
    ("kolkata", "Kolkata", "West Bengal", None),
    ("lucknow", "Lucknow", "Uttar Pradesh", None),
    ("mumbai", "Mumbai", "Maharashtra", None),
    ("new_delhi", "New Delhi", "Delhi", None),
    ("patna", "Patna", "Bihar", None),
    ("thiruvananthapuram", "Thiruvananthapuram", "Kerala", None),
)
