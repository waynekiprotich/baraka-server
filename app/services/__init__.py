"""Business logic.

Route handlers stay thin -- parse, validate, call one of these, serialize.
Queries, transactions and rules live here.
"""

from __future__ import annotations

from sqlalchemy import func, select

from ..extensions import db


def paginate(stmt, page: int, per_page: int) -> tuple[list, dict]:
    """Run a SELECT one page at a time and return (rows, envelope).

    The envelope is the shape every list endpoint returns:
    {items, page, per_page, total, pages} -- with `items` filled in by the
    caller once it has serialised the rows.
    """
    total = db.session.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
    pages = (total + per_page - 1) // per_page if per_page else 0
    rows = list(
        db.session.execute(stmt.limit(per_page).offset((page - 1) * per_page)).scalars().all()
    )
    return rows, {
        "items": [],
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": pages,
    }
