"""Reads the menu from the database and shapes it for the API."""

from hashlib import sha256

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, contains_eager, selectinload

from app import models, schemas

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
    group: models.OptionGroup, low: int | None = None, high: int | None = None
) -> schemas.OptionGroup:
    return schemas.OptionGroup(
        id=group.id,
        name=group.name,
        min_select=group.min_select if low is None else low,
        max_select=group.max_select if high is None else high,
        options=[schemas.Option.model_validate(o) for o in group.options],
    )


def _summary(p: models.Product) -> dict[str, object]:
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


def _detail(p: models.Product) -> schemas.ProductDetail:
    return schemas.ProductDetail(
        **_summary(p),  # type: ignore[arg-type]
        nutrition=p.nutrition,
        allergens=p.allergens,
        option_groups=[
            _group(link.group, link.min_select, link.max_select) for link in p.option_links
        ],
        meal_offers=[
            schemas.MealOffer(
                size=m.size,
                price_delta=m.price_delta,
                side=_group(m.side_group) if m.side_group else None,
                drink=_group(m.drink_group),
            )
            for m in p.meal_offers
        ],
    )


def categories(db: Session) -> list[schemas.Category]:
    rows = db.scalars(select(models.Category).order_by(models.Category.sort_order))
    return [schemas.Category(id=c.id, slug=c.slug, name=c.name) for c in rows]


def list_products(
    db: Session, category: str | None, veg: bool | None, q: str | None
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
    return [schemas.ProductSummary(**_summary(p)) for p in db.scalars(stmt)]  # type: ignore[arg-type]


def product(db: Session, product_id: int) -> schemas.ProductDetail | None:
    stmt = _active_products().where(models.Product.id == product_id).options(*DETAIL)
    found = db.scalars(stmt).first()
    return _detail(found) if found else None


def catalog(db: Session) -> schemas.Catalog:
    body = schemas.Catalog(
        version="",
        categories=categories(db),
        products=[_detail(p) for p in db.scalars(_active_products().options(*DETAIL))],
    )
    version = sha256(body.model_dump_json().encode()).hexdigest()[:12]
    return body.model_copy(update={"version": version})
