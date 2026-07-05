#!/usr/bin/env python3
"""
load_to_db.py — Load schema JSON files into PostgreSQL.
Usage: python load_to_db.py --dsn 'postgresql://user:pass@host/db'
Requires: pip install psycopg2-binary
"""
import json, argparse, psycopg2, psycopg2.extras
from pathlib import Path

def load(dsn: str, schema_dir: str):
    conn = psycopg2.connect(dsn)
    cur  = conn.cursor()

    schema_path = Path(schema_dir)

    # Apply DDL
    cur.execute(open(schema_path / 'schema.sql').read())

    # Load dimensions first (FK order)
    for table in ['banks', 'regions', 'complaint_categories', 'complaints_annual']:
        data = json.loads((schema_path / f'{table}.json').read_text())
        if not data:
            continue
        cols   = list(data[0].keys())
        values = [[r.get(c) for c in cols] for r in data]
        sql    = f"INSERT INTO {table} ({','.join(cols)}) VALUES %s ON CONFLICT DO NOTHING"
        psycopg2.extras.execute_values(cur, sql, values)
        print(f"  Loaded {len(data):,} rows into {table}")

    conn.commit()
    cur.close()
    conn.close()
    print("Done.")

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--dsn',    required=True)
    p.add_argument('--schema', default='schema')
    args = p.parse_args()
    load(args.dsn, args.schema)
