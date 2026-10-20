from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, orders, pricing, schemas
from app.database import get_db

router = APIRouter()


@router.post("/orders/price")
def price_order(request: schemas.PriceRequest, db: Session = Depends(get_db)) -> schemas.PricedCart:
    """Check a cart against the menu and price it. Nothing is saved."""
    if db.get(models.Outlet, request.outlet_id) is None:
        raise HTTPException(404, f"No outlet {request.outlet_id}")
    return pricing.price_cart(db, request.outlet_id, request.lines)


@router.post("/orders", status_code=201)
def create_order(request: schemas.OrderCreate, db: Session = Depends(get_db)) -> schemas.OrderOut:
    """Start a draft order: the cart."""
    return orders.view(orders.create(db, request))


@router.get("/orders/{order_id}")
def get_order(order_id: int, db: Session = Depends(get_db)) -> schemas.OrderOut:
    return orders.view(orders.get(db, order_id))


@router.post("/orders/{order_id}/lines", status_code=201)
def add_line(
    order_id: int, line: schemas.CartLine, db: Session = Depends(get_db)
) -> schemas.OrderOut:
    """Add one item. It must be complete and valid; otherwise 422 says what is missing or wrong
    and nothing is saved."""
    return orders.view(orders.add_line(db, order_id, line))


@router.delete("/orders/{order_id}/lines/{line_id}")
def remove_line(order_id: int, line_id: int, db: Session = Depends(get_db)) -> schemas.OrderOut:
    return orders.view(orders.remove_line(db, order_id, line_id))


@router.post("/orders/{order_id}/confirm")
def confirm_order(order_id: int, db: Session = Depends(get_db)) -> schemas.OrderOut:
    """Place the order. It is checked once more against the menu as it is now; if anything
    changed, 409 says what and the order stays a draft."""
    return orders.view(orders.confirm(db, order_id))
