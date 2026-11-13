from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from omni.db.agent import agent_session


class ItemLocationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_name: str = Field(min_length=1, max_length=200)
    location_name: str = Field(min_length=1, max_length=200)


class HorizonInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location_name: str | None = Field(default=None, max_length=200)
    within_days: int = Field(ge=1, le=365)


class ItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_name: str = Field(min_length=1, max_length=200)


class DocumentSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=500)


def _json_value(value: Any) -> Any:
    if isinstance(value, (date,)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _record(entity: str, row: Any) -> dict[str, Any]:
    values = {key: _json_value(value) for key, value in dict(row).items()}
    record_id = str(values.pop("record_id"))
    values.pop("entity", None)
    return {"entity": entity, "record_id": record_id, "fields": values}


def stock_history(value: ItemLocationInput) -> dict[str, Any]:
    query = text(
        """
        SELECT 'stock_level' AS entity, sl.id::text AS record_id,
               sl.quantity, sl.as_of AS occurred_on, sl.source_id::text AS source_id
        FROM stock_level AS sl
        JOIN item AS i ON i.id = sl.item_id
        JOIN location AS l ON l.id = sl.location_id
        WHERE i.name = :item_name AND l.name = :location_name
        UNION ALL
        SELECT 'stock_movement' AS entity, sm.id::text AS record_id,
               sm.quantity, sm.moved_on AS occurred_on,
               sm.source_id::text AS source_id
        FROM stock_movement AS sm
        JOIN item AS i ON i.id = sm.item_id
        JOIN location AS l
          ON l.id = sm.from_location_id OR l.id = sm.to_location_id
        WHERE i.name = :item_name AND l.name = :location_name
        ORDER BY occurred_on
        """
    )
    with agent_session() as session:
        rows = (
            session.execute(
                query,
                {"item_name": value.item_name, "location_name": value.location_name},
            )
            .mappings()
            .all()
        )
    return {"records": [_record(str(row["entity"]), row) for row in rows]}


def _forecast(
    session: Any,
    item_name: str,
    location_name: str,
) -> dict[str, Any]:
    current = (
        session.execute(
            text(
                """
                SELECT sl.id::text AS record_id, sl.quantity, sl.as_of,
                       i.name AS item_name, l.name AS location_name,
                       sl.source_id::text AS source_id
                FROM stock_level AS sl
                JOIN item AS i ON i.id = sl.item_id
                JOIN location AS l ON l.id = sl.location_id
                WHERE i.name = :item_name AND l.name = :location_name
                ORDER BY sl.as_of DESC
                LIMIT 1
                """
            ),
            {"item_name": item_name, "location_name": location_name},
        )
        .mappings()
        .first()
    )
    if current is None:
        raise ValueError("No current quantity was found for that item and location.")

    movement_rows = (
        session.execute(
            text(
                """
                SELECT sm.id::text AS record_id, sm.quantity, sm.moved_on,
                       i.name AS item_name, l.name AS location_name,
                       sm.source_id::text AS source_id
                FROM stock_movement AS sm
                JOIN item AS i ON i.id = sm.item_id
                JOIN location AS l ON l.id = sm.from_location_id
                WHERE i.name = :item_name AND l.name = :location_name
                ORDER BY sm.moved_on DESC
                """
            ),
            {"item_name": item_name, "location_name": location_name},
        )
        .mappings()
        .all()
    )
    monthly: dict[str, float] = defaultdict(float)
    for row in movement_rows:
        month = row["moved_on"].strftime("%Y-%m")
        monthly[month] += float(row["quantity"])
    recent = sorted(monthly.items())[-3:]
    if len(recent) < 3:
        raise ValueError("Not enough history: at least three monthly totals are required.")

    values = [amount for _, amount in recent]
    count = len(values)
    x_mean = (count - 1) / 2
    y_mean = sum(values) / count
    denominator = sum((index - x_mean) ** 2 for index in range(count))
    slope = (
        sum((index - x_mean) * (amount - y_mean) for index, amount in enumerate(values))
        / denominator
    )
    if slope <= 0:
        raise ValueError("No rising consumption trend in the recent monthly totals.")
    intercept = y_mean - slope * x_mean
    projected_monthly = max(0.0, intercept + slope * count)
    if projected_monthly <= 0:
        raise ValueError("No positive consumption trend supports a forecast.")

    quantity = float(current["quantity"])
    anchor = current["as_of"]
    projected_days = quantity / (projected_monthly / 30)
    half_spread = (max(values) - min(values)) / 2
    fastest_monthly = projected_monthly + half_spread
    slowest_monthly = projected_monthly - half_spread
    if slowest_monthly <= 0:
        raise ValueError("The recent totals do not provide a positive lower bound.")
    earliest_days = quantity / (fastest_monthly / 30)
    latest_days = quantity / (slowest_monthly / 30)
    predicted_date = anchor + timedelta(days=round(projected_days))
    earliest_date = anchor + timedelta(days=round(earliest_days))
    latest_date = anchor + timedelta(days=round(latest_days))

    stock_record = {
        "entity": "stock_level",
        "record_id": str(current["record_id"]),
        "quantity": quantity,
        "as_of": anchor,
        "source_id": current["source_id"],
    }
    evidence = [_record("stock_level", stock_record)]
    recent_months = {month for month, _ in recent}
    evidence.extend(
        _record("stock_movement", row)
        for row in movement_rows
        if row["moved_on"].strftime("%Y-%m") in recent_months
    )

    return {
        "item_name": item_name,
        "location_name": location_name,
        "predicted_runout_date": predicted_date.isoformat(),
        "earliest_date": earliest_date.isoformat(),
        "latest_date": latest_date.isoformat(),
        "estimated_days": round(projected_days, 1),
        "projected_monthly_use": round(projected_monthly, 1),
        "method": (
            "The linear trend gives the point estimate; half the observed "
            "monthly-use spread is added and subtracted for the faster and slower "
            "date bounds."
        ),
        "records": evidence,
    }


def item_demand_forecast(value: ItemLocationInput) -> dict[str, Any]:
    with agent_session() as session:
        return _forecast(session, value.item_name, value.location_name)


def items_within_horizon(value: HorizonInput) -> dict[str, Any]:
    with agent_session() as session:
        rows = (
            session.execute(
                text(
                    """
                    SELECT DISTINCT i.name AS item_name, l.name AS location_name
                    FROM stock_level AS sl
                    JOIN item AS i ON i.id = sl.item_id
                    JOIN location AS l ON l.id = sl.location_id
                    WHERE CAST(:location_name AS text) IS NULL
                       OR l.name = :location_name
                    ORDER BY i.name, l.name
                    """
                ),
                {"location_name": value.location_name},
            )
            .mappings()
            .all()
        )
        ranked: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        for row in rows:
            item_name = str(row["item_name"])
            location_name = str(row["location_name"])
            try:
                forecast = _forecast(session, item_name, location_name)
            except ValueError as error:
                skipped.append(
                    {
                        "item_name": item_name,
                        "location_name": location_name,
                        "reason": str(error),
                    }
                )
                continue
            if forecast["estimated_days"] <= value.within_days:
                ranked.append(forecast)
        ranked.sort(key=lambda item: item["estimated_days"])
    return {"items": ranked, "skipped": skipped}


def open_purchase_orders(value: ItemInput) -> dict[str, Any]:
    with agent_session() as session:
        rows = (
            session.execute(
                text(
                    """
                    SELECT po.id::text AS record_id, i.name AS item_name,
                           po.quantity, po.ordered_on,
                           po.promised_on, po.received_on, po.amount,
                           po.source_id::text AS source_id, s.name AS supplier_name
                    FROM purchase_order AS po
                    JOIN item AS i ON i.id = po.item_id
                    JOIN supplier AS s ON s.id = po.supplier_id
                    WHERE i.name = :item_name AND po.received_on IS NULL
                    ORDER BY po.promised_on NULLS LAST
                    """
                ),
                {"item_name": value.item_name},
            )
            .mappings()
            .all()
        )
    return {"records": [_record("purchase_order", row) for row in rows]}


def maintenance_jobs_using_item(value: ItemInput) -> dict[str, Any]:
    with agent_session() as session:
        rows = (
            session.execute(
                text(
                    """
                    SELECT DISTINCT mj.id::text AS record_id, mj.kind,
                           mj.opened_on, mj.closed_on, mj.fault,
                           mj.source_id::text AS source_id, a.name AS asset_name
                    FROM stock_movement AS sm
                    JOIN item AS i ON i.id = sm.item_id
                    JOIN maintenance_job AS mj ON mj.id = sm.maintenance_job_id
                    JOIN asset AS a ON a.id = mj.asset_id
                    WHERE i.name = :item_name
                    ORDER BY mj.opened_on DESC
                    """
                ),
                {"item_name": value.item_name},
            )
            .mappings()
            .all()
        )
    return {"records": [_record("maintenance_job", row) for row in rows]}


def search_documents(value: DocumentSearchInput) -> dict[str, Any]:
    with agent_session() as session:
        rows = (
            session.execute(
                text(
                    """
                    SELECT d.id::text AS record_id, d.title, d.kind,
                           d.authored_on, d.full_text,
                           d.source_id::text AS source_id
                    FROM document AS d
                    WHERE to_tsvector('simple', d.full_text)
                          @@ plainto_tsquery('simple', :query)
                    ORDER BY ts_rank(
                      to_tsvector('simple', d.full_text),
                      plainto_tsquery('simple', :query)
                    ) DESC
                    LIMIT 20
                    """
                ),
                {"query": value.query},
            )
            .mappings()
            .all()
        )
    return {"records": [_record("document", row) for row in rows]}
