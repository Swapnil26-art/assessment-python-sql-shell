# Data Assessment - Take-Home Solutions

> **Demo video (screen recording of all three solutions running end-to-end):**
> [https://www.loom.com/share/2fc8adc905b74129bf9d85416ff1d0f8](https://www.loom.com/share/2fc8adc905b74129bf9d85416ff1d0f8)

Solutions to the three-question take-home assessment:

| # | Question | Tech | Location |
|---|----------|------|----------|
| 1 | Scrape product search results from MD Computers | Python (requests + BeautifulSoup) | [`question-1-md-computers/`](question-1-md-computers/) |
| 2 | SQL questions on the public Rfam MySQL database | SQL (+ pymysql helper to run them) | [`question-2-rfam-sql/`](question-2-rfam-sql/) |
| 3 | Report S&P 500 companies by founding year | POSIX shell script (bash + awk + sort) | [`question-3-shell/`](question-3-shell/) |

Each folder contains its own sample output file produced by actually running
the code during development.

---

## Setup

```bash
# Python 3.9+ required for Question 1 and the Question 2 demo helper
pip install -r requirements.txt        # requests, beautifulsoup4, pymysql

# bash + curl + awk + sort required for Question 3
# (standard on Linux/macOS; Git Bash on Windows ships all of them)
```

## 1. MD Computers product scraper

```bash
cd question-1-md-computers

python mdcomputers_scraper.py "external harddrive"                 # JSON to stdout
python mdcomputers_scraper.py "external harddrive" -o sample_output.json
python mdcomputers_scraper.py "gaming keyboard" --format csv -o out.csv
python mdcomputers_scraper.py "external harddrive" --format table  # human view
python mdcomputers_scraper.py "external harddrive" --pages 1       # first page only
```

Verification run (also committed as `sample_output.json`):
`external harddrive` → **46 products** across 3 pages, which matches the
count the site itself reports ("Showing 1 to 20 of 46 (3 Pages)").

### How it works

The site runs OpenCart, so search results live at
`https://mdcomputers.in/?route=product/search&search=<term>&page=<n>`.
Each result card is a `div.product-grid-item` containing:

* `h3.product-entities-title a` - product name + product URL
* `span.price span.ins .amount` - current selling price
* `span.price span.del .amount` - struck-through original price
* `span.onsale.product-label` - discount badge (e.g. `-8%`)
* `ul.pagination` - links to further result pages

The crawler walks the numbered pagination links (skipping the `>` / `>|`
arrows), deduplicates by product URL, stops when a page adds nothing new,
limits itself to `--pages` if given, and sleeps ~1 s between page fetches.

### Design choices / extra credit

* **JSON as the default output format.** Data is inherently structured
  (name / price / discount / URL), prices are normalized to plain integers
  (`₹9,160` → `9160`) so they can be sorted or aggregated with no parsing,
  JSON round-trips losslessly with `json.load()`, and is the natural input
  for any downstream consumer (pandas, an API, etc.). Human-friendly `csv`
  and `--format table` views exist because graders and end-users don't
  always want JSON.
* **CSS selectors targeted at semantics** (`product-entities-title`,
  `price .ins/.del`, `onsale`) rather than positional/nth-child paths, so
  minor layout changes don't break extraction.
* **Robust prices:** `₹` and thousands separators are stripped at parse
  time; missing prices become `null` rather than `0`.
* **Deduplication by URL** avoids emitting duplicates when pagination
  overlaps; the loop's exit condition is "no new items found", which also
  guards against infinite pagination.
* **Politeness:** browser-like but honest `User-Agent`, a 1-second pause
  between pages, 30-second timeouts, and clean error messages on network
  failures (exit code 1, message on stderr, so stdout stays parseable).

## 2. Rfam database SQL

Connection details from the
[Rfam docs](https://docs.rfam.org/en/latest/database.html):

```
host: mysql-rfam-public.ebi.ac.uk   port: 4497   user: rfamro
password: (none)                    database: Rfam
```

Relevant schema: `taxonomy(ncbi_id, species, tax_string, ...)`,
`rfamseq(rfamseq_acc, ncbi_id, length, ...)`,
`family(rfam_acc, rfam_id, ...)`,
`full_region(rfam_acc, rfamseq_acc, is_significant, ...)`.

### The queries

Full, commented queries are in [`rfam_queries.sql`](question-2-rfam-sql/rfam_queries.sql).
To run them with the `mysql` client:

```bash
mysql --user rfamro --host mysql-rfam-public.ebi.ac.uk --port 4497 --database Rfam < rfam_queries.sql
```

Without a local MySQL client you can use the helper
([`run_queries.py`](question-2-rfam-sql/run_queries.py), pymysql - no server install needed):

```bash
cd question-2-rfam-sql
python run_queries.py          # Q1 (+ Q2, ~10 s - 2.5 min: server-side scan)
python run_queries.py --all    # also the Q3 heavy join (~4 min on average)
```

### Verified answers (from the live database)

**Q1 - How many types of Acacia plants are in the taxonomy table? → 326**

```sql
SELECT COUNT(*) AS num_acacia_types
FROM taxonomy
WHERE species LIKE 'Acacia%';
```

> Why not `tax_string LIKE '%Acacia%'`? We tested it: it returns **357**,
> but 31 of those rows are ***Arracacia*** (a carrot genus!) - "Arracacia"
> contains the substring "Acacia", and `tax_string` stores the full lineage
> including the genus name. Anchoring the match at the species name gives
> the correct 326. (Cross-check: `species LIKE 'Arracacia%'` → 31, and
> 326 + 31 = 357.)

**Q2 - Which type of wheat has the longest DNA sequence? → *Triticum durum* (durum wheat)**

```sql
SELECT t.species, r.rfamseq_acc, r.length
FROM rfamseq r JOIN taxonomy t ON r.ncbi_id = t.ncbi_id
WHERE t.tax_string LIKE '%Triticum%' OR t.species LIKE '%wheat%'
ORDER BY r.length DESC LIMIT 1;
```

Result: `Triticum durum (durum wheat) | LT934116.1 | 836,514,780 nt`
(~836.5 Mb) - ahead of *Triticum aestivum* (bread wheat) at 830,829,764 nt.

**Q3 - Families by longest sequence > 1,000,000 nt, descending, page 9, 15/page**

```sql
SELECT f.rfam_acc AS family_accession,
       f.rfam_id  AS family_name,
       MAX(r.length) AS max_sequence_length
FROM family f
JOIN full_region fr ON fr.rfam_acc   = f.rfam_acc
JOIN rfamseq r       ON r.rfamseq_acc = fr.rfamseq_acc
WHERE fr.is_significant = 1
GROUP BY f.rfam_acc, f.rfam_id
HAVING MAX(r.length) > 1000000
ORDER BY max_sequence_length DESC, family_accession ASC
LIMIT 15 OFFSET 120;   -- page 9 => skip (9-1)*15 = 120 rows
```

Page 9 rows (verified live) run from `RF01284 snoR8a` through
`RF04335 Plastid-rpl20`, all maxing out at 836,514,780 nt (that durum-wheat
contig again - many families are annotated on it), plus a stable tie-break
on accession so repeated runs paginate identically. `rfam_queries.sql`
also contains a pre-filtered variant that returns the identical page in
about half the time (`python run_queries.py --all` uses it; both were run
and compared during development).

## 3. S&P 500 companies by founding year

```bash
cd question-3-shell
chmod +x companies_report.sh
./companies_report.sh                                      # default dataset URL
./companies_report.sh <custom-csv-url>                     # any CSV URL
./companies_report.sh constituents.csv                     # or a local file
./companies_report.sh > sample_output.txt                  # capture evidence
```

Verified run: **503 companies** printed, oldest at the top
(`1792  State Street Corporation  Boston, Massachusetts`) to the newest
(`2026  Vylor  Johnston, Iowa`). Committed as `sample_output.txt`.

### Design choices

* **Accepts a URL as required by the brief** (and also local file paths -
  handy for offline demos), defaulting to the assessment's dataset URL.
* **RFC-4180-aware awk parser instead of `FS=','`.** Fields like
  `"Brown-Forman"` and `"Saint Paul, Minnesota"` contain commas inside
  quotes; a naive comma split would corrupt them. A small state machine in
  awk honours `"` quoting (opens/closes `in_q`), handles CRLF, and extracts
  fields 2 (name), 5 (location) and 8 (founded).
* **Founded-year rule, made explicit.** 36 of 503 rows are messy:
  `"2013 (1888)"`, `"1904/1946/1959"`, `"1994 (Northrop 1939, Grumman
  1930)"`. The script takes the **first 4-digit year** in the field - the
  founding of the entity the row describes - because the parenthetical
  years refer to predecessor companies/predecessor listings, and there's
  no unambiguous way to pick among them. (Change one line in the awk
  block if you prefer the earliest year.)
* **Sort: year ascending, name as tie-break**, with `LC_ALL=C sort` for
  deterministic byte-wise ordering across platforms. Tab is used as the
  internal separator precisely so it can never collide with real data.
* **Robustness:** `set -euo pipefail` (fail fast), `curl --retry 3`,
  missing HQ (`none`, e.g. Block, Inc.) printed as `(unknown)`, and rows
  with no year sink to the bottom instead of crashing.
* **Pure POSIX-ish tooling** (bash + curl + awk + sort): no jq/python
  dependency, runs anywhere including Git Bash on Windows.

## Screen recording

The terminal session above is demonstrated end-to-end in one screen recording
(watch it here):
**[Demo video - all three questions](https://www.loom.com/share/2fc8adc905b74129bf9d85416ff1d0f8)**

It shows, in order:

1. **Q1 (Python scraper)** - fetching MD Computers search results for
   "external harddrive", all 3 pages, output as a formatted table and as JSON
   (46 products, matching the site's own "of 46" count)
2. **Q3 (bash report)** - the shell script downloading the S&P 500 CSV and
   listing all 503 companies sorted by founding year (1792 -> 2026)
3. **Q2 (Rfam SQL)** - `run_queries.py` executing the three queries against
   the live Rfam public MySQL server and printing each answer: Q1 -> 326,
   Q2 -> Triticum durum / LT934116.1 / 836,514,780 nt, Q3 -> the page-9
   fifteen families with max sequence length 836,514,780 nt. The middle
   waiting periods are server-side scan/join time (~4-6 min total) that
   were trimmed from the video.

Approximate full runtimes, for reference:

| Script | Time |
|--------|------|
| Q1 scraper (3 pages) | ~10 s |
| Q3 shell script | ~2 - 4 s |
| Q2 `python run_queries.py --all` | ~4 min (dominated by server-side work) |

## Dependencies

* Python 3.9+ - `pip install -r requirements.txt`
* bash, curl, gawk (or mawk), sort - preinstalled on Linux/macOS and Git Bash
* Rfam queries: network access to `mysql-rfam-public.ebi.ac.uk:4497`
