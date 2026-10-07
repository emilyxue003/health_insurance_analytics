"""Export a read-only, connected synthetic sample and full-database aggregates."""

from datetime import datetime, timezone
import json
from pathlib import Path

from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select

from database import engine
from explorer import TABLE_NAMES, current_reporting_date, get_table, overview
from population_health import format_health, health_statement
from sql_showcase import full_showcase
from sqlalchemy import text


def export_demo(destination=None):
    as_of = current_reporting_date()
    summary = overview(as_of)
    tables = {name: get_table(name) for name in TABLE_NAMES}
    members = tables['MEMBERS']
    sample = {}

    def read(connection, name, statement):
        sample[name] = [dict(row) for row in connection.execute(statement).mappings()]

    with engine.connect() as connection:
        sql_evidence = full_showcase(lambda sql, params: [dict(row) for row in connection.execute(text(sql), params).mappings()],
                                     {row['name']: row['row_count'] for row in summary['tables']},
                                     'Full MySQL database', 'MySQL 8', True)
        health = format_health(connection.execute(health_statement(members)).mappings().one(), 'MySQL MEMBERS')
        read(connection, 'MEMBERS', select(members).order_by(members.c.member_id).limit(200))
        member_ids = [row['member_id'] for row in sample['MEMBERS']]
        for name, column in [('CLAIMS', 'member_id'), ('MEMBER_CONDITION', 'Member_ID')]:
            table = tables[name]
            read(connection, name, select(table).where(table.c[column].in_(member_ids)).order_by(*table.primary_key.columns))
        for name, member_column, target_column in [
            ('ENROLLMENT', 'Enrollment_ID', 'Enrollment_ID'),
            ('FACILITY', 'Primary_Care_Facility_ID', 'Facility_ID'),
        ]:
            ids = {row[member_column] for row in sample['MEMBERS'] if row[member_column] is not None}
            table = tables[name]
            read(connection, name, select(table).where(table.c[target_column].in_(ids)).order_by(*table.primary_key.columns))
        for name in ['CONDITION', 'INSURANCE', 'PLAN']:
            table = tables[name]
            read(connection, name, select(table).order_by(*table.primary_key.columns))
        states = [dict(row) for row in connection.execute(
            select(members.c.State.label('state'), func.count().label('count'))
            .group_by(members.c.State).order_by(members.c.State)
        ).mappings()]
        claims = tables['CLAIMS']
        trend = [dict(row) for row in connection.execute(
            select(func.date_format(claims.c.date, '%Y-%m').label('month'), func.sum(claims.c.amount).label('total'))
            .group_by('month').order_by('month')
        ).mappings()]

    schema = []
    for name, table in tables.items():
        keys = list(table.primary_key.columns.keys())
        assert len({tuple(row[key] for key in keys) for row in sample[name]}) == len(sample[name])
        foreign_keys = []
        for foreign_key in table.foreign_keys:
            target_name, target_column = foreign_key.target_fullname.rsplit('.', 1)
            target_name = target_name.rsplit('.', 1)[-1]
            target_ids = {row[target_column] for row in sample[target_name]}
            assert all(row[foreign_key.parent.name] is None or row[foreign_key.parent.name] in target_ids for row in sample[name]), f'Broken sample relationship: {name}.{foreign_key.parent.name}'
            foreign_keys.append({'column': foreign_key.parent.name, 'table': target_name, 'target_column': target_column})
        schema.append({'name': name, 'primary_key': keys, 'columns': list(table.columns.keys()), 'foreign_keys': foreign_keys})

    assert sum(row['count'] for row in states) == summary['total_members']
    assert sum(row['count'] for row in summary['age_distribution']) == summary['total_members']
    assert sum(row['count'] for row in summary['sex_distribution']) == summary['total_members']
    assert sum(row['count'] for row in summary['coverage_tiers']) == next(row['row_count'] for row in summary['tables'] if row['name'] == 'ENROLLMENT')
    assert abs(sum(float(row['total']) for row in trend) - summary['total_claims_value']) < 0.01

    payload = jsonable_encoder({
        'metadata': {
            'synthetic': True, 'as_of': as_of.isoformat(),
            'exported_at': datetime.now(timezone.utc).isoformat(),
            'sample_method': 'First 200 members by primary key and their related records. Reference tables CONDITION, INSURANCE, and PLAN are included in full. This sample is for interaction, not statistical inference.',
            'source_repository': 'https://github.com/emilyxue003/health_insurance_analytics',
        },
        'overview': summary, 'states': states, 'claims_trend': trend,
        'schema': schema, 'sample': sample, 'population_health': health,
        'sql_showcase': sql_evidence,
    })
    target = Path(destination) if destination else Path(__file__).resolve().parents[1] / 'frontend/public/demo/snapshot.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload, separators=(',', ':')), encoding='utf-8')
    temporary.replace(target)
    print(json.dumps({'path': str(target), 'as_of': as_of.isoformat(), 'full_records': sum(row['row_count'] for row in summary['tables']), 'sample_counts': {name: len(rows) for name, rows in sample.items()}, 'bytes': target.stat().st_size, 'validated': True}))


if __name__ == '__main__':
    export_demo()
