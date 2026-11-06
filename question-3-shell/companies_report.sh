#!/usr/bin/env bash
#
# companies_report.sh
# ------------------------------------------------------------------
# Fetches the S&P 500 constituents CSV (or any CSV at a user-supplied
# URL) and lists each company with its name, location and founding
# year, sorted by founding year.
#
# Data columns (constituents.csv):
#   1 Symbol  2 Security (name)  3 GICS Sector  4 GICS Sub-Industry
#   5 Headquarters Location  6 Date added  7 CIK  8 Founded
#
# "Founded" is messy data: values like "2013 (1888)", "1904/1946/1959",
# "1994 (Northrop 1939, Grumman 1930)". We take the FIRST 4-digit year
# in the field - the founding year of the entity the row describes - and
# document that choice in the README.
#
# Usage:
#   ./companies_report.sh                       # default dataset URL
#   ./companies_report.sh <csv-url>             # any CSV URL as argument
#   ./companies_report.sh local.csv             # or a local file path
#   ./companies_report.sh | head -20            # pipe, as usual
#
# Requirements: bash, curl, awk, sort  (all standard on Linux/macOS,
# and available in Git Bash on Windows).

set -euo pipefail

URL="https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
[[ $# -ge 1 ]] && URL="$1"

# Fetch the CSV: local files are read directly, remote URLs via curl.
if [[ -f "$URL" ]]; then
  DATA="$(cat "$URL")"
else
  DATA="$(curl -fsSL --retry 3 "$URL")"
fi

# Print the report:  founding_year, company name, location.
#  * $2 = Security (company name),  $5 = HQ location,  $8 = Founded.
#  * csv gsub() handles RFC-4180 fields: quoted "Name, Inc." / "City, State"
#    entries contain commas, so a plain FS=',' split would be wrong.
#  * The header row is skipped with NR > 1.
#  * loc placeholder "none" (Block, Inc. row) is shown as "unknown".
#  * The first 4-digit year in $8 is pulled with match() in a helper.
#  * Output rows go through sort: year ascending, ties broken by name;
#    LC_ALL=C keeps byte-wise order stable across platforms.
TAB="$(printf '\t')"                # tab as the field separator for sort
printf '%s' "$DATA" | awk '
function clean(s) { gsub(/"/, "", s); return s }
NR == 1 { next }
{
  split_csv5($0)
  name = clean(F[2]); loc = clean(F[5]); founded = F[8]

  # first 4-digit year in the Founded column (POSIX-safe regex)
  if (match(founded, /[0-9][0-9][0-9][0-9]/)) year = substr(founded, RSTART, 4)
  else year = 9999                 # no year found -> sinks to the bottom

  if (loc == "" || tolower(loc) == "none") loc = "(unknown)"
  printf "%s\t%s\t%s\n", year, name, loc
}
function split_csv5(line,   i, c, f, in_q, out) {
  # Split an RFC-4180 CSV record into F[1..8], honouring quotes.
  sub(/\r$/, "", line)              # tolerate Windows CRLF line endings
  out = ""; in_q = 0; delete F
  for (i = 1; i <= length(line); i++) {
    c = substr(line, i, 1)
    if (c == "\"") { in_q = (in_q ? 0 : 1); continue }
    if (c == "," && !in_q) { F[++f] = out; out = ""; continue }
    out = out c
  }
  F[++f] = out
}
' | LC_ALL=C sort -t "$TAB" -k1,1n -k2,2 | awk -F '\t' '
{
  printf "%-4s  %-45s  %s\n", $1, $2, $3
}
'
