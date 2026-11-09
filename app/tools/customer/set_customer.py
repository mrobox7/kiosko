"""set_customer: the customer gave their mobile number, so their usual dishes can be offered."""

from typing import Literal

from pydantic import BaseModel, Field

from app.backend.errors import BackendError, BackendRuleViolation
from app.backend.models import allergies_on_file
from app.menu.names import dish_name
from app.tools.backend_errors import settle
from app.tools.contract import Tool, ToolContext, ToolResult, Update

USUAL = 3  # how many of their most ordered dishes are brought back


class SetCustomerArgs(BaseModel):
    """Arguments of set_customer."""

    phone: str = Field(min_length=10, max_length=20)
    digits_confirmed: Literal[True]


class SetCustomer(Tool[SetCustomerArgs]):
    """Identify the customer by their mobile number."""

    name = "set_customer"
    args_model = SetCustomerArgs

    def run(self, ctx: ToolContext, args: SetCustomerArgs) -> ToolResult:
        try:
            customer = settle(
                lambda: ctx.backend.find_or_add_customer(args.phone), landed=lambda: None
            )
        except BackendRuleViolation:
            return ToolResult.failure(
                "invalid_phone",
                "That is not a valid mobile number.",
                "Ask the customer to say the ten digits again, then read them back.",
            )
        order = ctx.order
        if order is not None and order.status == "draft" and order.customer_id != customer.id:
            order = settle(
                lambda: ctx.backend.attach_customer(order.id, customer.id), landed=lambda: None
            )
        try:
            favourites = ctx.backend.get_favourites(customer.id, USUAL)
        except BackendError:
            favourites = []  # their usual dishes are a nicety: ordering goes on without them
        usual = [dish_name(f.name) for f in favourites]
        data: dict[str, object] = {"identified": True}
        if customer.name:
            data["name"] = customer.name
        if allergies := allergies_on_file(customer):
            data["allergies"] = allergies
        if usual:
            data["usual_dishes"] = usual
        update = Update(order=order, customer=customer, usual=usual)
        return ToolResult(ok=True, data=data, changed=True, update=update)
