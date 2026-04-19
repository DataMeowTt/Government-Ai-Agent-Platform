from fastapi import APIRouter
from sqlalchemy import text
from database.connect import get_engine

router = APIRouter()

# Loaded once at import time — zero latency on every request
def _load_tax_data() -> dict:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT country, tax_revenue FROM tax_revenue_2023"))
        return {row.country: row.tax_revenue for row in rows}

_TAX_DATA: dict = _load_tax_data()


@router.get("/tax-data")
def get_tax_data():
    return _TAX_DATA
