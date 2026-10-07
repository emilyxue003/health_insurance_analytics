"""Validate saved MySQL timing evidence without connecting to the database."""
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
from statistics import median

REPORT = Path(__file__).resolve().parent / 'benchmarks/mysql-performance.json'
OPTIMIZATION_REPORT = REPORT.with_name('mysql-optimization.json')
COVERING_REPORT = REPORT.with_name('mysql-covering-index.json')
ACTIVATION_REPORT = REPORT.with_name('mysql-covering-index-applied.json')
QUERY_NAMES = {'member_demographics', 'coverage_summary', 'population_health', 'monthly_claims',
               'members_by_state', 'member_lookup', 'members_first_page', 'regional_premiums',
               'housing_premiums', 'conditions_costs'}


def validate_report(report):
    if report['scope'] != 'full' or not report['mysql_version'].startswith('8.'):
        raise ValueError('Full MySQL 8 evidence is required.')
    datetime.fromisoformat(report['measured_at'])
    if not 3 <= report['repeats'] <= 20 or len(report['table_counts']) != 8:
        raise ValueError('Incomplete benchmark.')
    if any(type(n) is not int or n < 0 for n in report['table_counts'].values()):
        raise ValueError('Invalid table counts.')
    rows = report['results']
    if len(rows) != len(QUERY_NAMES) or {row['query'] for row in rows} != QUERY_NAMES:
        raise ValueError('All ten workloads are required.')
    for row in rows:
        if hashlib.sha256(row['sql'].encode()).hexdigest() != row['sql_sha256'] or not row['plan'].strip():
            raise ValueError('Missing or inconsistent query evidence.')
        trials = row['repeated_uncached_ms']
        values = trials + [row['first_read_ms'], row['median_repeated_ms']]
        if len(trials) != report['repeats'] or any(type(n) not in (int, float) or not math.isfinite(n) or n < 0 for n in values):
            raise ValueError('Invalid timings.')
        if abs(median(trials) - row['median_repeated_ms']) > 0.002:
            raise ValueError('Median does not reconcile.')
        if min(trials) != row['min_repeated_ms'] or max(trials) != row['max_repeated_ms']:
            raise ValueError('Timing range does not reconcile.')
    return report


def load_report():
    return validate_report(json.loads(REPORT.read_text()))


def validate_optimization(report, baseline):
    for field in ('mysql_version', 'connection', 'table_counts', 'parameters'):
        if report[field] != baseline[field]:
            raise ValueError('Comparison scope differs from the baseline.')
    datetime.fromisoformat(report['measured_at'])
    if not 3 <= report['repeats'] <= 20:
        raise ValueError('Invalid comparison repeat count.')
    expected = {'regional_grouped': 'regional_premiums', 'conditions_primary_diagnoses': 'conditions_costs',
                'conditions_primary_scans': 'conditions_costs'}
    if len(report['results']) != 3 or {r['candidate_name'] for r in report['results']} != set(expected):
        raise ValueError('Incomplete comparison.')
    originals = {row['query']: row for row in baseline['results']}
    for row in report['results']:
        if row['query'] != expected[row['candidate_name']] or row['results_equal'] is not True:
            raise ValueError('Invalid comparison result.')
        if row['result_sha256'] != originals[row['query']]['result_sha256']:
            raise ValueError('Comparison and saved baseline results differ.')
        for key in ('baseline', 'candidate'):
            side = row[key]
            if hashlib.sha256(side['sql'].encode()).hexdigest() != side['sql_sha256'] or not side['plan'].strip():
                raise ValueError('Comparison SQL or plan is inconsistent.')
            trials = side['repeated_uncached_ms']
            values = trials + [side['first_read_ms'], side['median_repeated_ms']]
            if len(trials) != report['repeats'] or any(type(n) not in (int, float) or not math.isfinite(n) or n <= 0 for n in values):
                raise ValueError('Invalid comparison timings.')
            if abs(median(trials) - side['median_repeated_ms']) > 0.002:
                raise ValueError('Comparison median does not reconcile.')
        before, after = [row[key]['median_repeated_ms'] for key in ('baseline', 'candidate')]
        if abs(row['speedup'] - before / after) > 0.002 or abs(row['change_pct'] - (after / before - 1) * 100) > 0.02:
            raise ValueError('Comparison improvement does not reconcile.')
    return report


def load_evidence():
    baseline = load_report()
    evidence = dict(baseline)
    if OPTIMIZATION_REPORT.exists():
        optimization = validate_optimization(json.loads(OPTIMIZATION_REPORT.read_text()), baseline)
        sql_path = Path(__file__).resolve().parents[1] / 'frontend/public/sql/regional_premiums.sql'
        regional = next(r for r in optimization['results'] if r['candidate_name'] == 'regional_grouped')
        adopted = ['regional_grouped'] if sql_path.read_text() == regional['candidate']['sql'] else []
        evidence.update(optimization=optimization, adopted_candidates=adopted)
    if COVERING_REPORT.exists():
        covering = validate_covering(json.loads(COVERING_REPORT.read_text()), baseline)
        evidence['covering_trial'] = covering
        if ACTIVATION_REPORT.exists():
            evidence['covering_activation'] = validate_activation(json.loads(ACTIVATION_REPORT.read_text()), covering)
    return evidence


def validate_covering(report, baseline):
    for field in ('mysql_version', 'connection', 'table_counts', 'parameters'):
        if report[field] != baseline[field]:
            raise ValueError('Covering trial scope differs from the baseline.')
    datetime.fromisoformat(report['measured_at'])
    if report['candidate_name'] != 'conditions_covering_claims' or report['query'] != 'conditions_costs' or report['results_equal'] is not True:
        raise ValueError('Unexpected covering trial.')
    if report['index_columns'] != ['member_id', 'date', 'amount'] or not 3 <= report['repeats'] <= 20:
        raise ValueError('Unexpected covering index or trials.')
    expected = next(r['result_sha256'] for r in baseline['results'] if r['query'] == 'conditions_costs')
    if report['result_sha256'] != expected:
        raise ValueError('Covering trial results differ from the full-data baseline.')
    for key in ('baseline', 'candidate'):
        side = report[key]
        if hashlib.sha256(side['sql'].encode()).hexdigest() != side['sql_sha256'] or not side['plan'].strip():
            raise ValueError('Invalid covering trial SQL or plan.')
        trials = side['repeated_uncached_ms']
        values = trials + [side['first_read_ms'], side['median_repeated_ms']]
        if len(trials) != report['repeats'] or any(type(n) not in (int, float) or not math.isfinite(n) or n <= 0 for n in values):
            raise ValueError('Invalid covering trial timings.')
        if abs(median(trials) - side['median_repeated_ms']) > 0.002:
            raise ValueError('Covering trial median does not reconcile.')
    before, after = [report[key]['median_repeated_ms'] for key in ('baseline', 'candidate')]
    if abs(report['speedup'] - before / after) > 0.002 or abs(report['change_pct'] - (after / before - 1) * 100) > 0.02:
        raise ValueError('Covering improvement does not reconcile.')
    if max(report['candidate']['repeated_uncached_ms']) >= min(report['baseline']['repeated_uncached_ms']):
        raise ValueError('Covering trial does not consistently improve on the reference.')
    return report


def load_covering():
    return validate_covering(json.loads(COVERING_REPORT.read_text()), load_report())


def validate_activation(report, trial):
    for field in ('mysql_version', 'connection', 'table_counts', 'parameters', 'index_name', 'index_columns', 'query', 'result_sha256'):
        if report[field] != trial[field]:
            raise ValueError('Activation differs from the verified covering trial.')
    if report['applied'] is not True or not 3 <= report['repeats'] <= 20:
        raise ValueError('Incomplete covering index activation.')
    if datetime.fromisoformat(report['measured_at']) < datetime.fromisoformat(trial['measured_at']):
        raise ValueError('Activation predates its trial.')
    current_sql = (Path(__file__).resolve().parents[1] / 'frontend/public/sql/conditions_costs.sql').read_text()
    if report['sql'] != current_sql or hashlib.sha256(report['sql'].encode()).hexdigest() != report['sql_sha256']:
        raise ValueError('Activation does not match the normal dashboard SQL.')
    if f"Covering index scan on CLAIMS using {report['index_name']}" not in report['plan']:
        raise ValueError('Activation plan does not use the verified index.')
    trials = report['repeated_uncached_ms']
    values = trials + [report['first_read_ms'], report['median_repeated_ms']]
    if len(trials) != report['repeats'] or any(type(n) not in (int, float) or not math.isfinite(n) or n <= 0 for n in values):
        raise ValueError('Invalid activation timings.')
    if abs(median(trials) - report['median_repeated_ms']) > 0.002:
        raise ValueError('Activation median does not reconcile.')
    if min(trials) != report['min_repeated_ms'] or max(trials) != report['max_repeated_ms']:
        raise ValueError('Activation timing range does not reconcile.')
    if max(trials) >= min(trial['baseline']['repeated_uncached_ms']):
        raise ValueError('Activation does not consistently improve on the saved reference.')
    return report
