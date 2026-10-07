"""Dashboard statements shared by live handlers and the MySQL benchmark."""
from sqlalchemy import func, select


def claims_trend_statement(table):
    month = func.date_format(table.c.date, '%Y-%m').label('month')
    return select(month, func.sum(table.c.amount).label('total')).group_by(month).order_by(month)


def members_by_state_statement(table):
    return select(table.c.State.label('state'), func.count(table.c.member_id).label('count')).group_by(table.c.State)
