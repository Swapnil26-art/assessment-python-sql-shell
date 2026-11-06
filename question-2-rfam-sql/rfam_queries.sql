-- ============================================================================
-- Rfam database questions  (read-only public MySQL server)
--
-- Connection (from https://docs.rfam.org/en/latest/database.html):
--   host:     mysql-rfam-public.ebi.ac.uk
--   port:     4497
--   user:     rfamro        password: (none)
--   database: Rfam
--
-- From a shell:
--   mysql --user rfamro --host mysql-rfam-public.ebi.ac.uk --port 4497 \
--         --database Rfam
--
-- Relevant tables (see the documentation page for the schema diagram):
--   taxonomy    : ncbi_id, species, tax_string, tree_display_name, align_display_name
--   rfamseq     : rfamseq_acc, ncbi_id, length, description, ...
--   family      : rfam_acc, rfam_id (family name), description, ...
--   full_region : rfam_acc, rfamseq_acc, seq_start, seq_end, is_significant, ...
-- ============================================================================


-- ---------------------------------------------------------------------------
-- Q1. How many types of Acacia plants can be found in the taxonomy table?
-- ---------------------------------------------------------------------------
-- The taxonomy table stores one row per organism; the `species` column holds
-- the scientific name. Rows for the genus Acacia all begin with "Acacia ".
--
-- NOTE ON WHY NOT `tax_string LIKE '%Acacia%'`:
--   A naive substring search of the whole lineage returns 357 rows, but that
--   over-counts by 31: the carrot genus *Arracacia* ("Arracacia nelsonii",
--   "Arracacia brandegei", ...) also contains the substring "Acacia".
--   Anchoring the match at the start of the species name avoids this.
--
-- ANSWER: 326 rows (i.e. 326 distinct Acacia species/subspecies entries).

SELECT COUNT(*) AS num_acacia_types
FROM taxonomy
WHERE species LIKE 'Acacia%';

-- Cross-check: `SELECT COUNT(*) FROM taxonomy WHERE species LIKE 'Arracacia%'`
-- returns 31  ->  326 + 31 = 357 explains the naive query's result exactly.


-- ---------------------------------------------------------------------------
-- Q2. Which type of wheat has the longest DNA sequence?
-- ---------------------------------------------------------------------------
-- Join rfamseq (all analysed sequences) to taxonomy via ncbi_id, filter the
-- lineage to the wheat genus Triticum, and order by sequence length.
-- Note: keep `tax_string` (full lineage) rather than `species`, so that
-- sub-species rows also match.
--
-- ANSWER: Triticum durum (durum wheat) - accession LT934116.1,
--         length 836,514,780 nt (~836.5 Mb), slightly ahead of
--         Triticum aestivum (bread wheat) at 830,829,764 nt.
--
-- Runtime note: rfamseq currently holds ~16M rows, so this join takes a few
-- minutes on the shared public server. A faster equivalent, if you already
-- know the taxonomy ids, is:
--   SELECT rf.rfamseq_acc, rf.length FROM rfamseq rf
--   WHERE rf.ncbi_id IN (4567)  ORDER BY rf.length DESC LIMIT 1;

SELECT t.species          AS wheat_type,
       r.rfamseq_acc      AS accession,
       r.length           AS dna_length_nt
FROM rfamseq AS r
JOIN taxonomy AS t ON r.ncbi_id = t.ncbi_id
WHERE t.tax_string LIKE '%Triticum%'     -- Triticum = wheat (genus/subtaxa)
  OR t.species LIKE '%wheat%'            -- common-name rows like "(bread wheat)"
ORDER BY r.length DESC
LIMIT 1;


-- ---------------------------------------------------------------------------
-- Q3. Paginate families by their longest DNA sequence length.
--     * only families whose longest sequence is greater than 1,000,000 nt
--     * sorted descending by that length
--     * columns: family accession, family name, maximum sequence length
--     * page 9 with 15 results per page  ->  OFFSET (9 - 1) * 15 = 120
-- ---------------------------------------------------------------------------
-- A family's regions live in full_region; each region points at a sequence in
-- rfamseq. We take the MAX(sequence length) per family over its *significant*
-- full-search regions, then paginate.
--
-- Runtime note: joins several million rows of full_region against rfamseq,
-- so expect ~4-8 minutes on the shared public server. (On one attempt the
-- server dropped the connection mid-query; the equivalent-but-faster form
-- kept below as "Q3-alternative" finished in ~3.5 min and returns the
-- identical 15 rows, because a per-family max > 1,000,000 can only come
-- from a sequence that is itself longer than 1,000,000 - so rfamseq can be
-- pre-filtered once before the join instead of being fully joined.)

SELECT f.rfam_acc                 AS family_accession,
       f.rfam_id                  AS family_name,
       MAX(r.length)              AS max_sequence_length
FROM family  AS f
JOIN full_region AS fr ON fr.rfam_acc  = f.rfam_acc
JOIN rfamseq     AS r  ON r.rfamseq_acc = fr.rfamseq_acc
WHERE fr.is_significant = 1              -- exclude low-scoring clan matches
GROUP BY f.rfam_acc, f.rfam_id
HAVING MAX(r.length) > 1000000
ORDER BY max_sequence_length DESC,
         family_accession ASC             -- deterministic tie-break: rows
                                          -- with equal max lengths always
                                          -- paginate in the same order
LIMIT 15
OFFSET 120;                              -- page 9 = (9-1) * 15 rows skipped

-- ---------------------------------------------------------------------------
-- Q3-alternative (same result page, ~2x faster on the shared server)
-- ---------------------------------------------------------------------------
SELECT f.rfam_acc                 AS family_accession,
       f.rfam_id                  AS family_name,
       MAX(r.length)              AS max_sequence_length
FROM family  AS f
JOIN full_region AS fr ON fr.rfam_acc  = f.rfam_acc
JOIN (SELECT rfamseq_acc, length FROM rfamseq WHERE length > 1000000) AS r
     ON r.rfamseq_acc = fr.rfamseq_acc
WHERE fr.is_significant = 1
GROUP BY f.rfam_acc, f.rfam_id
HAVING MAX(r.length) > 1000000
ORDER BY max_sequence_length DESC,
         family_accession ASC
LIMIT 15
OFFSET 120;
