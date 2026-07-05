OLLAMA_BASE   = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5:3b"
TIMEOUT       = 90         
RETRY_LIMIT   = 3
RETRY_DELAY   = 5          

# Minimum quality thresholds to keep a table
MIN_ROWS       = 3
MIN_COLS       = 2
MIN_NONEMPTY   = 5          
MAX_TABLE_ROWS = 10         
MAX_CTX_CHARS  = 350       

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "bankwise": [
        "bank group", "bank-wise", "bankwise", "bank wise",
        "scheduled commercial", "private sector bank", "public sector bank",
        "foreign bank", "rrb", "regional rural", "cooperative bank",
        "small finance bank", "payment bank", "sfb", "ucb",
        "nationalised bank", "new private",
    ],
    "categorywise": [
        "category", "nature of complaint", "complaint category",
        "ground of complaint", "type of complaint",
        "atm / debit", "credit card", "mobile banking", "internet banking",
        "loans and advance", "pension", "deposit account", "remittance",
        "insurance", "mis-selling", "sub-category",
    ],
    "disposal": [
        "disposal", "maintainability", "non-maintainable", "maintained",
        "resolved", "rejected", "withdrawn", "award", "settled",
        "closed", "disposed", "relief granted", "compensation",
        "mutual settlement", "sent to bank", "not pressed",
        "brought forward", "pending", "appeal",
    ],
    "officewise": [
        "ombudsman office", "obo", "office-wise", "office wise", "officewise",
        "zone", "zonal", "ahmedabad", "bengaluru", "bhopal", "bhubaneswar",
        "chandigarh", "chennai", "dehradun", "guwahati", "hyderabad",
        "jaipur", "jammu", "kanpur", "kolkata", "lucknow", "mumbai",
        "nagpur", "new delhi", "patna", "pune", "raipur", "ranchi",
        "thiruvananthapuram", "north zone", "south zone", "east zone",
        "west zone", "central zone",
    ],
}

