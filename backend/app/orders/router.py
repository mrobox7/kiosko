from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.menu.service import find_outlet
from app.orders import pricing, schemas, service

router = APIRouter()


@router.post("/orders/price")
def price_order(request: schemas.PriceRequest, db: Session = Depends(get_db)) -> schemas.PricedCart:
    """Check a cart against the menu and price it. Nothing is saved."""
    outlet = find_outlet(db, request.outlet)
    if outlet is None:
        raise HTTPException(404, f"No outlet {request.outlet}")
    return pricing.price_cart(db, outlet.id, request.lines)


@router.post("/orders", status_code=201)
def create_order(request: schemas.OrderCreate, db: Session = Depends(get_db)) -> schemas.OrderOut:
    """Start a draft order: the cart. A customer is optional and can be attached later."""
    return service.view(service.create(db, request))


@router.put("/orders/{order_id}/customer")
def attach_customer(
    order_id: int, body: schemas.AttachCustomer, db: Session = Depends(get_db)
) -> schemas.OrderOut:
    """Put a draft on a customer, for when they are identified after ordering began."""
    return service.view(service.attach_customer(db, order_id, body.customer_id))


@router.get("/orders/{order_id}")
def get_order(order_id: int, db: Session = Depends(get_db)) -> schemas.OrderOut:
    return service.view(service.get(db, order_id))


@router.post("/orders/{order_id}/lines", status_code=201)
def add_line(
    order_id: int, line: schemas.CartLine, db: Session = Depends(get_db)
) -> schemas.OrderOut:
    """Add one item. It must be complete and valid; otherwise 422 says what is missing or wrong
    and nothing is saved."""
    return service.view(service.add_line(db, order_id, line))


@router.delete("/orders/{order_id}/lines/{line_id}")
def remove_line(order_id: int, line_id: int, db: Session = Depends(get_db)) -> schemas.OrderOut:
    return service.view(service.remove_line(db, order_id, line_id))


@router.patch("/orders/{order_id}/lines/{line_id}")
def change_quantity(
    order_id: int, line_id: int, body: schemas.LineQuantity, db: Session = Depends(get_db)
) -> schemas.OrderOut:
    """Change how many of a line's item are wanted. The line keeps its id. To change anything
    else about an item, remove the line and add it again."""
    return service.view(service.set_quantity(db, order_id, line_id, body.quantity))


@router.delete("/orders/{order_id}")
def cancel_order(order_id: int, db: Session = Depends(get_db)) -> schemas.OrderOut:
    """Abandon a draft (the customer started over, left or timed out). It is kept as `cancelled`
    and can no longer change. Cancelling twice is fine; a confirmed order is 409."""
    return service.view(service.cancel(db, order_id))


@router.post("/orders/{order_id}/confirm")
def confirm_order(order_id: int, db: Session = Depends(get_db)) -> schemas.OrderOut:
    """Place the order. It is checked once more against the menu as it is now; if anything
    changed, 409 says what and the order stays a draft."""
    return service.view(service.confirm(db, order_id))
