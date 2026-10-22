"""Reads the menu from the database and shapes it for the API."""

from hashlib import sha256

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, contains_eager, selectinload

from app.menu import models, schemas
from app.menu.availability import Availability

_GROUP_WITH_OPTIONS = selectinload(models.OptionGroup.options)

DETAIL = (
    selectinload(models.Product.option_links)
    .selectinload(models.ProductOptionGroup.group)
    .options(_GROUP_WITH_OPTIONS),
    selectinload(models.Product.meal_offers)
    .selectinload(models.MealOffer.side_group)
    .options(_GROUP_WITH_OPTIONS),
    selectinload(models.Product.meal_offers)
    .selectinload(models.MealOffer.drink_group)
    .options(_GROUP_WITH_OPTIONS),
)


def _active_products() -> Select[models.Product]:
    """Active products in menu order, with their category."""
    return (
        select(models.Product)
        .join(models.Product.category)
        .where(models.Product.is_active)
        .options(contains_eager(models.Product.category))
        .order_by(models.Category.sort_order, models.Product.sort_order, models.Product.id)
    )


def _group(
    group: models.OptionGroup,
    sale: Availability,
    low: int | None = None,
    high: int | None = None,
) -> schemas.OptionGroup:
    return schemas.OptionGroup(
        id=group.id,
        name=group.name,
        min_select=group.min_select if low is None else low,
        max_select=group.max_select if high is None else high,
        options=[schemas.Option.model_validate(o) for o in sale.options(group)],
    )


def find_outlet(db: Session, code: str) -> models.Outlet | None:
    return db.scalar(select(models.Outlet).where(models.Outlet.code == code))


def _menu(
    db: Session, stmt: Select[models.Product], outlet: models.Outlet | None
) -> tuple[list[models.Product], Availability]:
    """The products of `stmt` that the outlet sells (all of them with no outlet)."""
    sale = Availability.for_outlet(db, outlet.id) if outlet else Availability()
    return [p for p in db.scalars(stmt.options(*DETAIL)) if sale.sells(p)], sale


def _summary(p: models.Product, sale: Availability) -> dict[str, object]:
    return {
        "id": p.id,
        "sku": p.sku,
        "name": p.name,
        "description": p.description,
        "kind": p.kind,
        "veg": p.veg,
        "category": p.category.slug,
        "base_price": p.base_price,
        "image_url": f"/{p.image_key}" if p.image_key else None,
        "tags": p.tags,
    }


def _detail(p: models.Product, sale: Availability) -> schemas.ProductDetail:
    return schemas.ProductDetail(
        **_summary(p, sale),  # type: ignore[arg-type]
        nutrition=p.nutrition,
        allergens=p.allergens,
        option_groups=[
            _group(link.group, sale, link.min_select, link.max_select) for link in p.option_links
        ],
        meal_offers=[
            schemas.MealOffer(
                size=m.size,
                price_delta=m.price_delta,
                side=_group(m.side_group, sale) if m.side_group else None,
                drink=_group(m.drink_group, sale),
            )
            for m in p.meal_offers
            if sale.meal_ok(m)
        ],
    )


def categories(db: Session) -> list[schemas.Category]:
    rows = db.scalars(select(models.Category).order_by(models.Category.sort_order))
    return [schemas.Category(id=c.id, slug=c.slug, name=c.name) for c in rows]


def list_products(
    db: Session, category: str | None, veg: bool | None, q: str | None, outlet: models.Outlet | None
) -> list[schemas.ProductSummary]:
    stmt = _active_products()
    if category:
        stmt = stmt.where(models.Category.slug == category)
    if veg is not None:
        stmt = stmt.where(models.Product.veg == ("veg" if veg else "non_veg"))
    if q:
        stmt = stmt.where(
            models.Product.name.icontains(q, autoescape=True)
            | models.Product.description.icontains(q, autoescape=True)
        )
    products, sale = _menu(db, stmt, outlet)
    return [schemas.ProductSummary(**_summary(p, sale)) for p in products]  # type: ignore[arg-type]


def product(
    db: Session, product_id: int, outlet: models.Outlet | None
) -> schemas.ProductDetail | None:
    products, sale = _menu(db, _active_products().where(models.Product.id == product_id), outlet)
    return _detail(products[0], sale) if products else None


def catalog(db: Session, outlet: models.Outlet | None) -> schemas.Catalog:
    products, sale = _menu(db, _active_products(), outlet)
    body = schemas.Catalog(
        version="",
        categories=categories(db),
        products=[_detail(p, sale) for p in products],
    )
    version = sha256(body.model_dump_json().encode()).hexdigest()[:12]
    return body.model_copy(update={"version": version})


def unavailable(db: Session, outlet: models.Outlet) -> schemas.Unavailable:
    """What the outlet has switched off."""
    products = select(models.UnavailableProduct.product_id).where(
        models.UnavailableProduct.outlet_id == outlet.id
    )
    options = select(models.UnavailableOption.option_id).where(
        models.UnavailableOption.outlet_id == outlet.id
    )
    return schemas.Unavailable(
        products=sorted(db.scalars(products)), options=sorted(db.scalars(options))
    )


def switch_product(db: Session, outlet: models.Outlet, product_id: int, off: bool) -> bool:
    """Stop (or resume) selling a product at the outlet. False if there is no such product.
    Doing it twice is harmless."""
    if db.get(models.Product, product_id) is None:
        return False
    row = db.get(models.UnavailableProduct, (outlet.id, product_id))
    if off and row is None:
        db.add(models.UnavailableProduct(outlet_id=outlet.id, product_id=product_id))
    elif not off and row is not None:
        db.delete(row)
    db.commit()
    return True


def switch_option(db: Session, outlet: models.Outlet, option_id: int, off: bool) -> bool:
    """Stop (or resume) offering an option at the outlet. False if there is no such option."""
    if db.get(models.Option, option_id) is None:
        return False
    row = db.get(models.UnavailableOption, (outlet.id, option_id))
    if off and row is None:
        db.add(models.UnavailableOption(outlet_id=outlet.id, option_id=option_id))
    elif not off and row is not None:
        db.delete(row)
    db.commit()
    return True
