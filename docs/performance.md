# Query performance evidence

The workload contains 32,400,574 synthetic records across eight tables, including 5,000,000 members and 13,179,693 claims. All reports were produced on local MySQL 8.0.45 on October 6, 2026. The coverage cutoff is November 30, 2025; claims run from November 1, 2024 through November 30, 2025, with an exclusive December 1 end date.

## Regional preaggregation

The original query applied window calculations to approximately 3.15 million eligible enrollment records. The adopted version groups by state, plan, and coverage tier first, reducing window inputs to 8,000 cells while retaining original enrollment weights.

Median paired query time fell from 17.774 s to 7.482 s, a 57.91% reduction and 2.376 times speedup. Complete result checksums matched. Every repeated candidate read was faster than every repeated reference read.

- [Original SQL](../frontend/public/sql/baselines/regional_premiums.sql)
- [Applied SQL](../frontend/public/sql/regional_premiums.sql)
- [Comparison report](../backend/benchmarks/mysql-optimization.json)

The same report preserves two rejected conditions scan hints. The diagnosis scan improved 4.60%, but trial ranges overlapped. Changing diagnosis and claims scans together was 2.20% slower. Neither hint is applied.

## Covering claims index

The plan showed costly claims row fetches through the existing member/date secondary index. A covering index on `CLAIMS(member_id, date, amount)` supplies the amount needed for aggregation directly from the index.

It was initially invisible and enabled only within the benchmark session. Three alternating paired repeats measured 38.189 s with the existing index versus 23.446 s with the covering index, a 38.60% reduction and 1.629 times speedup. Complete result checksums matched. Index construction took 6.061 s, recorded separately from query timings.

After activation, the unchanged unhinted dashboard query chose the visible covering index automatically. Three repeated reads measured a 18.917 s median. This later activation check is separate from the paired trial; it is not a paired 38.189 to 18.917 s speedup estimate.

- [Paired trial](../backend/benchmarks/mysql-covering-index.json)
- [Normal-query activation verification](../backend/benchmarks/mysql-covering-index-applied.json)
- [Opt-in index benchmark](../backend/benchmark_covering_index.py)
- [Activation and rollback checks](../backend/activate_covering_index.py)

The index adds storage and write maintenance work. Write performance and index size were not measured. A visible index can affect other optimizer choices; the activation study verified the normal conditions query, not a new measurement of every dashboard endpoint.

## Measurement scope

The [original ten-query baseline](../backend/benchmarks/mysql-performance.json) retains first reads, three repeated reads, exact SQL and parameters, table counts, indexes, result checksums, and execution plans. Member lookup measured 0.826 ms and the first table page measured 1.052 ms; the page includes 25 records plus one lookahead.

Timings include fetching results. They exclude connection setup, HTTP, application caching, browser rendering, metadata checks, and index creation. Metadata reads warmed database buffers; buffers were not flushed. One client ran the trials, and background load was not controlled. These measurements do not establish cold-disk, concurrent-user, or Cloud SQL performance.

The five-minute API cache is an application behavior, separate from query optimization. Each API process has its own cache. The full premium endpoint also performs reconciliation queries, so end-to-end loading time exceeds a single analytical SELECT's timing.

## Reproduce

Use a database containing the same complete synthetic data, schema, and parameters. The included sample cannot reproduce the full-data timings.

From `backend`, with a configured MySQL environment:

```sh
python benchmark_mysql.py
python compare_mysql.py
HEALTHPULSE_CREATE_COVERING_INDEX=1 python benchmark_covering_index.py
python activate_covering_index.py
```

The first two commands run read-only SELECTs. The third explicitly permits creating a missing invisible covering index and requires appropriate privileges. The fourth makes the verified index visible and attempts to restore its previous visibility if verification fails. Existing records are unchanged. Review reports before adopting an optimization; the scripts do not infer speedups from caches or fixture timings.
