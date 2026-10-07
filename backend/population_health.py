"""Descriptive health measures with explicit missing-value denominators."""

import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path

from sqlalchemy import and_, case, func, select

MEASURES = {
    'heart_rate': ('heart_rate', [(0, 60, 'Below 60'), (60, 80, '60–79'), (80, 100, '80–99'), (100, None, '100+')]),
    'sleep': ('hours_sleep_per_day', [(0, 6, 'Below 6 hours'), (6, 8, '6 to under 8'), (8, None, '8+ hours')]),
    'exercise': ('minutes_exercise_per_week', [(0, 1, '0 minutes'), (1, 60, '1–59 minutes'), (60, 150, '60–149 minutes'), (150, None, '150+ minutes')]),
}
BEHAVIORS = [('smoker', 'Recorded smoker'), ('drinker', 'Recorded drinker')]
CSV_FIELDS = {'heart_rate': 'heart_rate', 'hours_sleep_per_day': 'sleep_hours_per_night',
              'minutes_exercise_per_week': 'exercise_minutes_per_week', 'smoker': 'smoker', 'drinker': 'drinker'}


def numeric(value):
    if value is None or str(value).strip().lower() in ('', 'null', 'none', 'nan', '\\n'):
        return None
    result = float(value)
    return result if math.isfinite(result) and result >= 0 else None


def health_statement(table):
    expressions = [func.count().label('total')]
    for key, (column, bins) in MEASURES.items():
        value = table.c[column]
        valid = and_(value.is_not(None), value >= 0)
        expressions.extend([func.avg(case((valid, value), else_=None)).label(f'{key}_average'),
                            func.sum(case((valid, 1), else_=0)).label(f'{key}_known')])
        for index, (lower, upper, _) in enumerate(bins):
            condition = and_(valid, value >= lower, value < upper) if upper is not None else and_(valid, value >= lower)
            expressions.append(func.sum(case((condition, 1), else_=0)).label(f'{key}_{index}'))
    for column, _ in BEHAVIORS:
        for value in (0, 1):
            expressions.append(func.sum(case((table.c[column] == value, 1), else_=0)).label(f'{column}_{value}'))
    return select(*expressions).select_from(table)


def format_health(row, source):
    total = int(row['total'])
    averages, distributions = {}, {}
    for key, (_, bins) in MEASURES.items():
        known = int(row[f'{key}_known'] or 0)
        average = row[f'{key}_average']
        averages[key] = {'value': round(float(average), 1) if average is not None else None, 'count': known, 'missing': total - known}
        distributions[key] = [{'label': label, 'count': int(row[f'{key}_{index}'] or 0)} for index, (_, _, label) in enumerate(bins)]
        distributions[key].append({'label': 'Missing / invalid', 'count': total - known})
        assert sum(item['count'] for item in distributions[key]) == total
    behaviors = []
    for column, label in BEHAVIORS:
        no, yes = int(row[f'{column}_0'] or 0), int(row[f'{column}_1'] or 0)
        behaviors.append({'key': column, 'label': label, 'yes': yes, 'no': no, 'unknown': total - yes - no})
    return {'total_members': total, 'source': source, 'averages': averages, 'distributions': distributions, 'behaviors': behaviors}


def summarize_rows(rows):
    totals = {'total': 0}
    for key, (_, bins) in MEASURES.items():
        totals[f'{key}_sum'] = 0.0
        totals[f'{key}_known'] = 0
        for index in range(len(bins)):
            totals[f'{key}_{index}'] = 0
    for column, _ in BEHAVIORS:
        totals[f'{column}_0'], totals[f'{column}_1'] = 0, 0
    for row in rows:
        totals['total'] += 1
        for key, (column, bins) in MEASURES.items():
            value = numeric(row[column])
            if value is None:
                continue
            totals[f'{key}_sum'] += value
            totals[f'{key}_known'] += 1
            for index, (lower, upper, _) in enumerate(bins):
                if value >= lower and (upper is None or value < upper):
                    totals[f'{key}_{index}'] += 1
                    break
        for column, _ in BEHAVIORS:
            value = numeric(row[column])
            if value in (0, 1):
                totals[f'{column}_{int(value)}'] += 1
    for key in MEASURES:
        known = totals[f'{key}_known']
        totals[f'{key}_average'] = totals[f'{key}_sum'] / known if known else None
    return totals


def enrich_demo():
    root = Path(__file__).resolve().parents[1]
    path = root / 'frontend/public/demo/snapshot.json'
    original = path.read_bytes()
    snapshot = json.loads(original)
    sample = {str(row['member_id']): row for row in snapshot['sample']['MEMBERS']}
    checked = set()
    source = root / 'database/members.csv'
    before = source.stat()

    def rows():
        with source.open(newline='') as file:
            for number, record in enumerate(csv.DictReader(file), 1):
                normalized = {column: numeric(record[csv_column]) for column, csv_column in CSV_FIELDS.items()}
                if record['member_id'] in sample:
                    member = sample[record['member_id']]
                    assert all(normalized[column] == member[column] for column in CSV_FIELDS), 'Source health measures differ from saved sample.'
                    checked.add(record['member_id'])
                if number % 1000000 == 0:
                    print(f'Aggregated {number:,} source member records.', flush=True)
                yield normalized

    health = format_health(summarize_rows(rows()), 'MEMBERS source CSV')
    assert len(checked) == len(sample)
    assert health['total_members'] == snapshot['overview']['total_members']
    assert health['averages']['heart_rate']['value'] == snapshot['overview']['average_heart_rate']
    after = source.stat()
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns), 'Source changed during aggregation.'
    assert path.read_bytes() == original, 'Demo snapshot changed during aggregation.'
    health['generated_at'] = datetime.now(timezone.utc).isoformat()
    health['verified_sample_members'] = len(checked)
    snapshot['population_health'] = health
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(snapshot, separators=(',', ':')))
    temporary.replace(path)
    print(json.dumps({'total_members': health['total_members'], 'averages': health['averages'], 'behaviors': health['behaviors'], 'sample_records_reconciled': len(checked)}))


if __name__ == '__main__':
    enrich_demo()
