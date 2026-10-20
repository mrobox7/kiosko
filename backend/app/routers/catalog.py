from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import catalog, schemas
from app.database import get_db

router = APIRouter()


@router.get("/categories")
def get_categories(db: Session = Depends(get_db)) -> list[schemas.Category]:
    return catalog.categories(db)


@router.get("/products")
def get_products(
    category: str | None = None,
    veg: bool | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
) -> list[schemas.ProductSummary]:
    """Items on the menu. `category` is a category slug; `q` matches name or description."""
    return catalog.list_products(db, category, veg, q)


@router.get("/products/{product_id}")
def get_product(product_id: int, db: Session = Depends(get_db)) -> schemas.ProductDetail:
    """One item with everything the customer can choose: option groups and meal offers."""
    found = catalog.product(db, product_id)
    if found is None:
        raise HTTPException(404, f"No product {product_id}")
    return found


@router.get("/catalog")
def get_catalog(db: Session = Depends(get_db)) -> schemas.Catalog:
    """The whole menu in one response, for building a search index."""
    return catalog.catalog(db)
