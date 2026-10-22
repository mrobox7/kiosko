from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.customers import models, schemas, service
from app.database import get_db
from app.orders import service as order_service
from app.orders.schemas import OrderOut

router = APIRouter()


def _customer(db: Session, customer_id: int) -> models.Customer:
    found = db.get(models.Customer, customer_id)
    if found is None:
        raise HTTPException(404, f"No customer {customer_id}")
    return found


@router.post("/customers")
def identify_customer(
    request: schemas.CustomerCreate, response: Response, db: Session = Depends(get_db)
) -> schemas.CustomerOut:
    """Find the customer by mobile number or add them: 201 when new, 200 when already known."""
    customer, created = service.identify(db, request)
    response.status_code = 201 if created else 200
    return schemas.CustomerOut.model_validate(customer)


@router.get("/customers/{customer_id}")
def get_customer(customer_id: int, db: Session = Depends(get_db)) -> schemas.CustomerOut:
    return schemas.CustomerOut.model_validate(_customer(db, customer_id))


@router.patch("/customers/{customer_id}/preferences")
def update_preferences(
    customer_id: int, body: schemas.PreferencesUpdate, db: Session = Depends(get_db)
) -> schemas.CustomerOut:
    """Merge keys into the preferences (diet, allergies, anything). Other keys stay."""
    customer = _customer(db, customer_id)
    service.update_preferences(db, customer, body.preferences)
    return schemas.CustomerOut.model_validate(customer)


@router.get("/customers/{customer_id}/orders")
def customer_orders(
    customer_id: int, limit: int = Query(10, ge=1, le=50), db: Session = Depends(get_db)
) -> list[OrderOut]:
    """Confirmed orders, newest first."""
    _customer(db, customer_id)
    return [order_service.view(o) for o in service.confirmed_orders(db, customer_id, limit)]


@router.get("/customers/{customer_id}/favourites")
def customer_favourites(
    customer_id: int, limit: int = Query(5, ge=1, le=20), db: Session = Depends(get_db)
) -> list[schemas.Favourite]:
    """What this customer orders most, from past confirmed orders. Items taken off the menu are
    left out."""
    _customer(db, customer_id)
    return service.favourites(db, customer_id, limit)


@router.get("/customers/{customer_id}/draft")
def customer_draft(customer_id: int, db: Session = Depends(get_db)) -> OrderOut:
    """The latest unfinished cart that has items in it; 404 if there is none."""
    _customer(db, customer_id)
    draft = service.open_draft(db, customer_id)
    if draft is None:
        raise HTTPException(404, "No unfinished order")
    return order_service.view(draft)
