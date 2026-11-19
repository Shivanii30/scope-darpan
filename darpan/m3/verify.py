import sqlite3

con = sqlite3.connect(r"C:\Users\kshiv\Downloads\banking\final\darpan\m3\outputs\darpan.sqlite")
tables = ("banks", "regions", "complaint_categories", "complaints_annual", "bank_financials", "staging_tables")
print({table: con.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] for table in tables})
print("year_count", con.execute("SELECT COUNT(DISTINCT year) FROM complaints_annual").fetchone()[0])
con.close()
