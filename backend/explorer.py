"""Read-only dashboard aggregates and bounded table browsing."""

import base64
import binascii
from collections import OrderedDict
from datetime import date, datetime, timezone
from functools import lru_cache, wraps
import json
import logging
from threading import Condition
from time import monotonic
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response
from sqlalchemy import MetaData, Table, and_, case, func, or_, select, text
from sqlalchemy.exc import SQLAlchemyError

from database import engine
from population_health import format_health, health_statement
from sql_showcase import PARAMETERS, full_showcase

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get('/api/stats/query-performance')
def query_performance():
    from performance_evidence import load_evidence
    try:
        report = load_evidence()
        return Response(json.dumps(report), media_type='application/json',
                        headers={'Content-Disposition': 'attachment; filename="healthpulse-mysql-performance.json"'})
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(503, 'Saved MySQL measurement is unavailable.') from None


TABLE_NAMES = (
    'MEMBERS', 'CLAIMS', 'ENROLLMENT', 'FACILITY', 'CONDITION',
    'INSURANCE', 'PLAN', 'MEMBER_CONDITION',
)
AGE_BANDS = ((0, 18, '0–17'), (18, 35, '18–34'), (35, 45, '35–44'),
             (45, 55, '45–54'), (55, 65, '55–64'), (65, 75, '65–74'))
CACHE_TTL = 300


class TTLCache:
    """Bounded cache with one in-flight loader per key in this process."""

    def __init__(self, ttl=CACHE_TTL, max_entries=32, clock=monotonic):
        self.ttl, self.max_entries, self.clock = ttl, max_entries, clock
        self.entries = OrderedDict()
        self.running = set()
        self.condition = Condition()

    def get(self, key, loader):
        with self.condition:
            while True:
                entry = self.entries.get(key)
                if entry and self.clock() - entry[0] < self.ttl:
                    self.entries.move_to_end(key)
                    return entry[1]
                if key not in self.running:
                    self.running.add(key)
                    break
                self.condition.wait()
        try:
            result = loader()
            with self.condition:
                self.entries[key] = (self.clock(), result)
                self.entries.move_to_end(key)
                while len(self.entries) > self.max_entries:
                    self.entries.popitem(last=False)
            return result
        finally:
            with self.condition:
                self.running.discard(key)
                self.condition.notify_all()


cache = TTLCache()


def database_read(loader):
    try:
        return loader()
    except SQLAlchemyError as exc:
        logger.warning('Dashboard database request failed (%s)', type(exc).__name__)
        raise HTTPException(503, 'Database results are temporarily unavailable.') from None


def cached_endpoint(key):
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            return database_read(lambda: cache.get(key, lambda: function(*args, **kwargs)))
        return wrapped
    return decorate


@lru_cache(maxsize=8)
def get_table(name):
    if name not in TABLE_NAMES:
        raise HTTPException(404, 'Unknown table.')
    return Table(name, MetaData(), autoload_with=engine, resolve_fks=False)


def current_reporting_date():
    return datetime.now(ZoneInfo('America/Chicago')).date()


def member_statement(table, as_of):
    age = func.timestampdiff(text('YEAR'), table.c.DOB, as_of)
    valid = and_(table.c.DOB.is_not(None), table.c.DOB <= as_of)
    expressions = [func.count().label('total'), func.avg(table.c.heart_rate).label('heart_rate')]
    for lower, upper, label in AGE_BANDS:
        expressions.append(func.sum(case((and_(valid, age >= lower, age < upper), 1), else_=0)).label(label))
    expressions.append(func.sum(case((and_(valid, age >= 75), 1), else_=0)).label('75+'))
    for sex in ('F', 'M', 'O'):
        expressions.append(func.sum(case((table.c.Sex == sex, 1), else_=0)).label(sex))
    return select(*expressions).select_from(table)


def member_aggregates(as_of):
    table = get_table('MEMBERS')
    with engine.connect() as connection:
        row = connection.execute(member_statement(table, as_of)).mappings().one()
    total = row['total']
    ages = [{'band': label, 'count': int(row[label] or 0)} for label in [x[2] for x in AGE_BANDS] + ['75+']]
    ages.append({'band': 'Unknown / future DOB', 'count': total - sum(x['count'] for x in ages)})
    sexes = [{'sex': sex, 'count': int(row[sex] or 0)} for sex in ('F', 'M', 'O')]
    sexes.append({'sex': 'Unknown', 'count': total - sum(x['count'] for x in sexes)})
    return {'total': total, 'average_heart_rate': round(float(row['heart_rate']), 1) if row['heart_rate'] is not None else None,
            'age_distribution': ages, 'sex_distribution': sexes}


def coverage_statement(table, as_of):
    active = and_(table.c.start_date <= as_of, or_(table.c.end_date.is_(None), table.c.end_date >= as_of))
    return select(table.c.Coverage_tier.label('tier'), func.count().label('count'),
                       func.sum(case((active, 1), else_=0)).label('active')).group_by(table.c.Coverage_tier)


def coverage_aggregates(as_of):
    table = get_table('ENROLLMENT')
    with engine.connect() as connection:
        rows = connection.execute(coverage_statement(table, as_of)).mappings().all()
    tiers = sorted([{'tier': row['tier'] or 'Unknown', 'count': row['count']} for row in rows], key=lambda row: (-row['count'], row['tier']))
    return {'total': sum(row['count'] for row in rows), 'active': sum(int(row['active'] or 0) for row in rows), 'tiers': tiers}


def inventory_aggregates():
    counts = {}
    claims_total = None
    with engine.connect() as connection:
        for name in TABLE_NAMES:
            if name in ('MEMBERS', 'ENROLLMENT'):
                continue
            table = get_table(name)
            if name == 'CLAIMS':
                row = connection.execute(select(func.count(), func.sum(table.c.amount)).select_from(table)).one()
                counts[name], claims_total = row[0], float(row[1]) if row[1] is not None else None
            else:
                counts[name] = connection.scalar(select(func.count()).select_from(table))
    return {'counts': counts, 'total_claims_value': claims_total}


@router.get('/api/explorer/overview')
def overview(as_of: date | None = None):
    reference_date = as_of or current_reporting_date()

    def load():
        members = cache.get(('members', reference_date), lambda: member_aggregates(reference_date))
        coverage = cache.get(('coverage', reference_date), lambda: coverage_aggregates(reference_date))
        inventory = cache.get('inventory', inventory_aggregates)
        counts = {**inventory['counts'], 'MEMBERS': members['total'], 'ENROLLMENT': coverage['total']}
        tables = [{'name': name, 'row_count': counts[name], 'columns': list(get_table(name).columns.keys()),
                   'primary_key': list(get_table(name).primary_key.columns.keys())} for name in TABLE_NAMES]
        return {'as_of': reference_date.isoformat(), 'generated_at': datetime.now(timezone.utc).isoformat(),
                'cache_ttl_seconds': CACHE_TTL, 'tables': tables,
                'total_members': members['total'], 'total_claims': counts['CLAIMS'],
                'total_claims_value': inventory['total_claims_value'], 'average_heart_rate': members['average_heart_rate'],
                'active_enrollments': coverage['active'], 'age_distribution': members['age_distribution'],
                'sex_distribution': members['sex_distribution'], 'coverage_tiers': coverage['tiers']}

    return database_read(lambda: cache.get(('overview', reference_date), load))


def encode_cursor(table, row):
    payload = {'table': table.name, 'values': [jsonable_encoder(row[column.name]) for column in table.primary_key.columns]}
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(',', ':')).encode()).decode().rstrip('=')


def decode_cursor(table, cursor):
    try:
        if len(cursor) > 4096:
            raise ValueError()
        payload = json.loads(base64.b64decode(cursor + '=' * (-len(cursor) % 4), altchars=b'-_', validate=True))
        values = payload['values']
        keys = list(table.primary_key.columns)
        if payload['table'] != table.name or not isinstance(values, list) or len(values) != len(keys):
            raise ValueError()
        parsed = []
        for column, value in zip(keys, values):
            kind = column.type.python_type
            if kind is date:
                parsed.append(date.fromisoformat(value))
            elif kind is int and type(value) is int and 0 <= value <= 2**64 - 1:
                parsed.append(value)
            else:
                raise ValueError()
        return parsed
    except (ValueError, TypeError, KeyError, binascii.Error, UnicodeError, OverflowError):
        raise HTTPException(400, 'Invalid cursor for this table.') from None


def page_statement(table, limit, cursor=None):
    keys = list(table.primary_key.columns)
    if not keys:
        raise HTTPException(503, 'This table has no stable browsing key.')
    statement = select(table)
    if cursor:
        values = decode_cursor(table, cursor)
        statement = statement.where(or_(*[
            and_(*[keys[j] == values[j] for j in range(i)], keys[i] > values[i])
            for i in range(len(keys))
        ]))
    return statement.order_by(*keys).limit(limit + 1)


@router.get('/api/tables/{table_name}')
def table_page(table_name: str, limit: int = Query(25, ge=1, le=100), cursor: str | None = Query(None, max_length=4096)):
    def load():
        table = get_table(table_name)
        with engine.connect() as connection:
            rows = [dict(row) for row in connection.execute(page_statement(table, limit, cursor)).mappings()]
        has_more = len(rows) > limit
        rows = rows[:limit]
        return {'table': table_name, 'columns': list(table.columns.keys()), 'rows': jsonable_encoder(rows),
                'next_cursor': encode_cursor(table, rows[-1]) if has_more else None, 'has_more': has_more}
    return database_read(load)


@router.get('/api/stats/population-health')
@cached_endpoint('population-health')
def population_health():
    with engine.connect() as connection:
        row = connection.execute(health_statement(get_table('MEMBERS'))).mappings().one()
    return format_health(row, 'MySQL MEMBERS')


@router.get('/api/stats/premium-equity')
def premium_equity(as_of: date = date.fromisoformat(PARAMETERS['as_of']),
                   claims_start: date = date.fromisoformat(PARAMETERS['claims_start']),
                   claims_end: date = date.fromisoformat(PARAMETERS['claims_end']),
                   minimum_peers: int = Query(2, ge=2, le=1000)):
    if claims_start >= claims_end or claims_end.toordinal() > as_of.toordinal() + 1:
        raise HTTPException(400, 'Claims must have a positive interval ending no later than the day after the coverage cutoff.')
    parameters = {'as_of': as_of.isoformat(), 'claims_start': claims_start.isoformat(),
                  'claims_end': claims_end.isoformat(), 'minimum_peers': minimum_peers}
    def load():
        with engine.connect() as connection:
            connection.execute(text('SET TRANSACTION READ ONLY'))
            connection.execute(text('START TRANSACTION WITH CONSISTENT SNAPSHOT'))
            def read(sql, bound):
                return [dict(r) for r in connection.execute(text(sql), bound).mappings()]
            counts = {name: connection.scalar(select(func.count()).select_from(get_table(name)))
                      for name in ('MEMBERS', 'ENROLLMENT', 'CLAIMS', 'MEMBER_CONDITION')}
            result = full_showcase(read, counts, 'Full MySQL database', 'MySQL 8', True, parameters)
            schema = []
            for name in TABLE_NAMES:
                table = get_table(name)
                keys = []
                for key in table.foreign_keys:
                    target, column = key.target_fullname.rsplit('.', 1)
                    keys.append({'column': key.parent.name, 'table': target.rsplit('.', 1)[-1], 'target_column': column})
                schema.append({'name': name, 'primary_key': list(table.primary_key.columns.keys()), 'foreign_keys': keys})
            connection.rollback()
        return jsonable_encoder({'sql_showcase': result, 'schema': schema})
    return database_read(lambda: cache.get(('premium-equity', *parameters.values()), load))


@router.get('/api/stats/premium-equity/export')
def export_premium_equity(case_id: str, minimum_state_count: int = Query(0, ge=0),
                          as_of: date = date.fromisoformat(PARAMETERS['as_of']),
                          claims_start: date = date.fromisoformat(PARAMETERS['claims_start']),
                          claims_end: date = date.fromisoformat(PARAMETERS['claims_end']),
                          minimum_peers: int = Query(2, ge=2, le=1000)):
    if case_id not in ('regional_premiums', 'housing_premiums', 'conditions_costs'):
        raise HTTPException(404, 'Unknown premium analysis.')
    data = premium_equity(as_of, claims_start, claims_end, minimum_peers)['sql_showcase']
    selected = next(c for c in data['cases'] if c['id'] == case_id)
    rows = [r for r in selected['rows'] if r['enrollments'] >= minimum_state_count] if case_id == 'regional_premiums' else selected['rows']
    payload = {**{k: data[k] for k in ('source', 'scope', 'total_members', 'parameters', 'engine', 'mysql_verified', 'generated_at')},
               'question': selected['question'], 'grain': selected['grain'], 'sql_sha256': selected['sha256'],
               'state_minimum_count': minimum_state_count if case_id == 'regional_premiums' else None,
               'methods_document': 'https://healthpulse-analytics.netlify.app/sql/README.md',
               'caveat': 'Synthetic descriptive comparison. Premium billing frequency is undocumented. This is not an income, affordability, causal fairness, or discrimination estimate.',
               'rows': rows}
    return Response(json.dumps(jsonable_encoder(payload), indent=2), media_type='application/json',
                    headers={'Content-Disposition': f'attachment; filename="healthpulse-{case_id}-results.json"'})
