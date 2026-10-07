# HealthPulse backend

FastAPI and SQLAlchemy provide local read-only exploration and full-database premium analyses. See the root README for the hosted demo, SQL case studies, and source scope.

## Setup

Requires Python 3.12 and MySQL 8. From this folder:

```sh
python3.12 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Replace the example settings locally. Use the isolated sample database instructions in `database/README.md` for a reproducible small dataset. Start the API with `python run_dashboard.py`; it listens on `http://127.0.0.1:8001`. Start Vite from the frontend folder and open `http://localhost:5173`. Keep both Terminal windows open. Backend changes require a restart.

API startup does not create tables. Use a database account granted SELECT for dashboard reads. Index experiments require a separate account with the necessary schema privileges. This local API has no public authentication layer; the hosted demo is static and contains no database connection.

## Routes

| Route | Behavior |
| :- | :- |
| `/api/explorer/overview?as_of=YYYY-MM-DD` | Table counts, claims value, demographics, coverage tiers, and schema metadata |
| `/api/tables/{table_name}?limit=25&cursor=...` | Allowlisted table pages, ordered by the complete primary key; page sizes 1 to 100 |
| `/members/{member_id}` | Individual member lookup |
| `/api/stats/population-health` | Recorded health and behavior distributions with explicit missing or invalid buckets |
| `/api/stats/claims-trend` | Monthly claim amounts |
| `/api/stats/members-by-state` | Member counts by state |
| `/api/stats/premium-equity` | Three premium analyses in a read-only consistent transaction, plus reconciliation and schema |
| `/api/stats/premium-equity/export` | Displayed result export with scope, parameters, SQL hash, and interpretation limits |
| `/api/stats/query-performance` | Validated historical benchmark evidence; it does not run a fresh timing study |

The premium parameters are `as_of`, `claims_start`, `claims_end` (exclusive), and `minimum_peers` (2 to 1000). Defaults use a November 30, 2025 coverage cutoff and November 2024 through November 2025 claims. Claims end must follow start and be no later than the day after the cutoff. Export additionally requires an allowlisted `case_id` and accepts `minimum_state_count` for regional display filtering.

## Analytical integrity and runtime behavior

The SQL preaggregates diagnoses and claims before joining members. Counts and claim totals reconcile with direct joins, and enrollment-weighted regional indices reconcile to 100. Decimal arithmetic supports MySQL aggregate numeric types. Period boundaries, missing links, repeated diagnoses, zero claims, zero premiums, unavailable comparison groups, and empty inputs are tested.

Age uses completed years on the reporting date; missing or future birth dates have an explicit bucket. Coverage-tier counts describe enrollment records across all periods. Active enrollments include inclusive start/end boundaries and an open missing end date. The overview date affects age and active coverage, not all-record counts or claim totals.

Aggregate results are cached for five minutes by parameter set. Concurrent requests for the same cache key share one calculation in that process. Each API process has its own cache. Table pages and member lookups are uncached. Cursor validation preserves composite keys, including diagnosis date. Reads use bound parameters; database errors return generic responses without raw connection details. The first premium request also performs validation queries, so its wall-clock duration exceeds an individual SELECT timing.

## Tests

```sh
python -m unittest discover
```

Two MySQL checks are opt-in with `HEALTHPULSE_LIVE_TESTS=1 python -m unittest test_explorer`. The GitHub workflow runs them against an isolated MySQL sample service and reconciles all three real sample query outputs against independent Python calculations. Sample checks do not establish full-scale performance.

## Exports and benchmarks

| Command | Purpose and side effects |
| :- | :- |
| `python run_sql_showcase_mysql.py` | Execute the three SELECTs read-only and print results |
| `python export_demo.py` | Read MySQL and write reviewed synthetic aggregates and a connected sample locally |
| `python export_full_sql.py` | Execute all source CSV rows in a temporary SQLite projection; raw CSVs are required and excluded from Git |
| `python benchmark_mysql.py` | Ten full-data SELECT workloads; save counts, parameters, indexes, plans, checksums, and direct timings |
| `python compare_mysql.py` | Paired read-only comparison of three query rewrites; no active SQL or indexes changed |
| `HEALTHPULSE_CREATE_COVERING_INDEX=1 python benchmark_covering_index.py` | Explicitly permit creation of a missing invisible covering claims index, then compare scan paths |
| `python activate_covering_index.py` | Make the verified index visible and check the normal query; attempt restoration on failed verification |
| `python publish_performance.py` | Attach reconciled saved evidence to the demo snapshot and public downloads |

The index script consumes storage and adds maintenance work. It does not remove an index if a later benchmark fails. Activation restores prior visibility when verification fails and restoration can complete. Connection failure during restoration requires manual inspection. Original stored records are unchanged.

Reports in `benchmarks` preserve the ten-query baseline, paired regional and conditions alternatives, covering-index trial, and normal-query activation check. Their exact scope and exclusions are documented in `docs/performance.md`. They measured local MySQL, not Cloud SQL, concurrent requests, or browser latency. Reproducing the full timing study requires the original complete dataset; the included sample is for functional review.
