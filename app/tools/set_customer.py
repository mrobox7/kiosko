"""set_customer: the customer gave their mobile number, so their usual dishes can be offered."""

from typing import Literal

from pydantic import BaseModel, Field

from app.backend.errors import BackendError, BackendRuleViolation
from app.domain.results import ToolResult
from app.menu.names import dish_name
from app.tools.base import Tool, ToolContext
from app.tools.recover import settle

USUAL = 3  # how many of their most ordered dishes are brought back


class SetCustomerArgs(BaseModel):
    """Arguments of set_customer."""

    phone: str = Field(min_length=10, max_length=20)
    digits_confirmed: Literal[True]


class SetCustomer(Tool[SetCustomerArgs]):
    """Identify the customer by their mobile number."""

    name = "set_customer"
    description = (
        "Only when the customer offers their mobile number (never ask for it to order): to "
        "recognise them and bring back the allergies on file and the dishes they usually order. "
        "Speech recognition mishears digits, so read the number back to them in groups and send "
        "`digits_confirmed` as true only after they say it is right; a wrong number would create "
        "or open someone else's record. The reply gives their `name` if known, `allergies` and "
        "`usual_dishes`. Do not read the number or past orders back to them. The order, if one "
        "has been started, stays and is put on their record."
    )
    args_model = SetCustomerArgs
    mutating = True

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
        order = ctx.order.latest
        if order is not None and order.status == "draft" and order.customer_id != customer.id:
            ctx.order.latest = settle(
                lambda: ctx.backend.attach_customer(order.id, customer.id), landed=lambda: None
            )
        try:
            favourites = ctx.backend.get_favourites(customer.id, USUAL)
        except BackendError:
            favourites = []  # their usual dishes are a nicety: ordering goes on without them
        ctx.caller.customer = customer
        ctx.caller.usual = [dish_name(f.name) for f in favourites]
        data: dict[str, object] = {"identified": True}
        if customer.name:
            data["name"] = customer.name
        if ctx.caller.allergies:
            data["allergies"] = ctx.caller.allergies
        if ctx.caller.usual:
            data["usual_dishes"] = ctx.caller.usual
        return ToolResult(ok=True, data=data, changed=True)

    def compact(self, result: ToolResult, args: SetCustomerArgs) -> str:
        if not result.ok:
            code = result.error.code if result.error else "error"
            return f"customer: not set ({code})"
        usual = result.data.get("usual_dishes")
        return "customer identified" + (f", usually {', '.join(usual)}" if usual else "")
