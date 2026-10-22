from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.menu import models, schemas, service

router = APIRouter()


def _known(db: Session, code: str) -> models.Outlet:
    found = service.find_outlet(db, code)
    if found is None:
        raise HTTPException(404, f"No outlet {code}")
    return found


def _outlet(db: Session, code: str | None) -> models.Outlet | None:
    """The outlet asking, or None for the menu with no outlet's changes applied."""
    return None if code is None else _known(db, code)


@router.get("/products")
def get_products(
    category: str | None = None,
    veg: bool | None = None,
    q: str | None = None,
    outlet: str | None = None,
    db: Session = Depends(get_db),
) -> list[schemas.ProductSummary]:
    """Items on the menu. `category` is a category slug; `q` matches name or description.
    With `outlet` (its code), items that outlet does not sell are left out and its prices are
    used."""
    return service.list_products(db, category, veg, q, _outlet(db, outlet))


@router.get("/products/{product_id}")
def get_product(
    product_id: int, outlet: str | None = None, db: Session = Depends(get_db)
) -> schemas.ProductDetail:
    """One item with everything the customer can choose: option groups and meal offers."""
    found = service.product(db, product_id, _outlet(db, outlet))
    if found is None:
        raise HTTPException(404, f"No product {product_id}")
    return found


@router.get("/catalog")
def get_catalog(outlet: str | None = None, db: Session = Depends(get_db)) -> schemas.Catalog:
    """The whole menu in one response, for building a search index. With `outlet` (its code),
    it is that outlet's menu."""
    return service.catalog(db, _outlet(db, outlet))


@router.get("/catalog/version")
def get_catalog_version(
    outlet: str | None = None, db: Session = Depends(get_db)
) -> schemas.CatalogVersion:
    """Only the version of `/catalog`, so a client can tell whether its copy is out of date
    without downloading the menu."""
    return schemas.CatalogVersion(version=service.catalog(db, _outlet(db, outlet)).version)


@router.get("/outlets/{code}")
def get_outlet(code: str, db: Session = Depends(get_db)) -> schemas.OutletInfo:
    """The outlet's name and address."""
    found = _known(db, code)
    return schemas.OutletInfo(code=found.code, name=found.name, address=found.address)


@router.get("/outlets/{code}/unavailable")
def get_unavailable(code: str, db: Session = Depends(get_db)) -> schemas.Unavailable:
    """The products and options (by id) this outlet is not selling right now."""
    return service.unavailable(db, _known(db, code))


@router.put("/outlets/{code}/unavailable/products/{product_id}", status_code=204)
def stop_selling_product(code: str, product_id: int, db: Session = Depends(get_db)) -> Response:
    """The outlet has run out of, or stopped making, this product."""
    if not service.switch_product(db, _known(db, code), product_id, off=True):
        raise HTTPException(404, f"No product {product_id}")
    return Response(status_code=204)


@router.delete("/outlets/{code}/unavailable/products/{product_id}", status_code=204)
def resume_selling_product(code: str, product_id: int, db: Session = Depends(get_db)) -> Response:
    if not service.switch_product(db, _known(db, code), product_id, off=False):
        raise HTTPException(404, f"No product {product_id}")
    return Response(status_code=204)


@router.put("/outlets/{code}/unavailable/options/{option_id}", status_code=204)
def stop_offering_option(code: str, option_id: int, db: Session = Depends(get_db)) -> Response:
    """The outlet has run out of this option, such as a drink or a sauce."""
    if not service.switch_option(db, _known(db, code), option_id, off=True):
        raise HTTPException(404, f"No option {option_id}")
    return Response(status_code=204)


@router.delete("/outlets/{code}/unavailable/options/{option_id}", status_code=204)
def resume_offering_option(code: str, option_id: int, db: Session = Depends(get_db)) -> Response:
    if not service.switch_option(db, _known(db, code), option_id, off=False):
        raise HTTPException(404, f"No option {option_id}")
    return Response(status_code=204)
