#!/usr/bin/env python3
"""
run_queries.py
--------------
Helper that executes the SQL answers in rfam_queries.sql against the public
Rfam MySQL server and prints the results. Useful for demonstrating the
queries without a locally installed `mysql` client.

Usage:
    python run_queries.py            # runs Q1 and Q2 (fast)
    python run_queries.py --all      # also runs Q3 pagination (~5-8 min,
                                     #  heavy join on the shared server)

Requires:  pip install pymysql
"""

from __future__ import annotations

import argparse
import sys
import time

import pymysql

HOST = "mysql-rfam-public.ebi.ac.uk"
PORT = 4497
USER = "rfamro"
DATABASE = "Rfam"

# ---------------------------------------------------------------------------
# The three answers. Each query is kept in sync with rfam_queries.sql.
# ---------------------------------------------------------------------------
Q1 = (
    "How many types of Acacia plants are in the taxonomy table?",
    "SELECT COUNT(*) AS num_acacia_types FROM taxonomy WHERE species LIKE 'Acacia%'",
)

Q2 = (
    "Which type of wheat has the longest DNA sequence?",
    "SELECT t.species AS wheat_type, r.rfamseq_acc AS accession, r.length AS dna_length_nt "
    "FROM rfamseq r JOIN taxonomy t ON r.ncbi_id = t.ncbi_id "
    "WHERE t.tax_string LIKE '%Triticum%' OR t.species LIKE '%wheat%' "
    "ORDER BY r.length DESC LIMIT 1",
)

Q3 = (
    "Families by longest sequence > 1,000,000 nt - page 9, 15 per page",
    "SELECT f.rfam_acc AS family_accession, f.rfam_id AS family_name, "
    "MAX(r.length) AS max_sequence_length "
    "FROM family f "
    "JOIN full_region fr ON fr.rfam_acc = f.rfam_acc "
    "JOIN rfamseq r ON r.rfamseq_acc = fr.rfamseq_acc "
    "WHERE fr.is_significant = 1 "
    "GROUP BY f.rfam_acc, f.rfam_id "
    "HAVING MAX(r.length) > 1000000 "
    "ORDER BY max_sequence_length DESC, family_accession ASC "
    "LIMIT 15 OFFSET 120",
)


def run(cur, label: str, sql: str) -> None:
    print(f"\n{'=' * 70}\n{label}\n{'-' * 70}\nSQL: {sql}\n{'-' * 70}")
    t0 = time.time()
    cur.execute(sql)
    rows = cur.fetchall()
    for row in rows:
        print("  ", " | ".join(str(v) for v in row))
    print(f"--- {len(rows)} row(s) in {time.time() - t0:.1f}s", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true",
                        help="also run the slow Q3 pagination query")
    args = parser.parse_args()

    print(f"Connecting to {HOST}:{PORT} as {USER} ...", flush=True)
    conn = pymysql.connect(
        host=HOST, user=USER, password="", port=PORT, database=DATABASE,
        charset="utf8mb4", connect_timeout=30, read_timeout=900,
    )
    try:
        with conn.cursor() as cur:
            run(cur, f"Q1: {Q1[0]}", Q1[1])
            run(cur, f"Q2: {Q2[0]}", Q2[1])
            if args.all:
                run(cur, f"Q3: {Q3[0]} (this joins ~millions of rows, be patient)", Q3[1])
            elif not args.all:
                print("\n(Q3 skipped; run with --all to execute it - takes ~5-8 min)")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
