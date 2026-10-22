"""What one outlet sells: the menu with that outlet's changes applied.

An outlet can switch off a product or an option. The rest follows from those switches:
- an option that points at a product is off when that product is off (or not on the menu);
- a question stays only with the answers that are on, and a product with a required question that
  has no answers left is off too (a combo whose every burger choice is off);
- a meal upgrade is off when its side or drink question can no longer be answered."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.menu.models import (
    MealOffer,
    Option,
    OptionGroup,
    Product,
    UnavailableOption,
    UnavailableProduct,
)


class Availability:
    """With no arguments nothing is switched off."""

    def __init__(
        self,
        off_products: set[int] | None = None,
        off_options: set[int] | None = None,
        inactive_products: set[int] | None = None,
    ) -> None:
        self._off_products = off_products or set()
        self._off_options = off_options or set()
        # products an option can no longer point at: switched off, or not on the menu
        self._gone_products = self._off_products | (inactive_products or set())

    @classmethod
    def for_outlet(cls, db: Session, outlet_id: int) -> Availability:
        off_products = set(
            db.scalars(
                select(UnavailableProduct.product_id).where(
                    UnavailableProduct.outlet_id == outlet_id
                )
            )
        )
        off_options = set(
            db.scalars(
                select(UnavailableOption.option_id).where(UnavailableOption.outlet_id == outlet_id)
            )
        )
        inactive = set(db.scalars(select(Product.id).where(~Product.is_active)))
        return cls(off_products, off_options, inactive)

    def has(self, option: Option) -> bool:
        return option.id not in self._off_options and option.linked_product_id not in (
            self._gone_products
        )

    def options(self, group: OptionGroup) -> list[Option]:
        return [option for option in group.options if self.has(option)]

    def _answerable(self, group: OptionGroup, low: int | None = None) -> bool:
        """A required question needs one answer left; the same answer can be picked again."""
        need = group.min_select if low is None else low
        return need == 0 or bool(self.options(group))

    def meal_ok(self, offer: MealOffer) -> bool:
        groups = (offer.side_group, offer.drink_group)
        return all(self._answerable(group) for group in groups if group is not None)

    def sells(self, product: Product) -> bool:
        if product.id in self._off_products:
            return False
        return all(self._answerable(link.group, link.min_select) for link in product.option_links)
