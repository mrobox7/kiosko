from app.backend.models import Customer
from app.domain.state import ActiveOrder, Caller
from app.session.context_builder import HEADING, build_context
from app.session.prompts import STABLE_PROMPT, VOICE_PROMPT, system_prompt
from tests.support.builders import NOW, make_order_tools

ASHA = Customer(id=3, name="Asha Rao", phone="+919876543210", email=None)


def test_context_has_heading_time_customer_and_an_empty_order() -> None:
    context = build_context(NOW, ActiveOrder(), Caller())
    assert context.startswith(f"{HEADING}:")
    assert "Saturday 2030-06-01 12:00" in context
    assert "Customer: not identified" in context and "Order so far: empty" in context


def test_the_order_is_listed_with_line_ids_and_totals() -> None:
    ctx, _, tools = make_order_tools()
    tools.dispatch("add_to_order", {"dish_id": 4, "quantity": 2, "note": "no onion"}, ctx)
    context = build_context(NOW, ctx.order, Caller())
    assert "- line 10: 2 x McAloo Tikki, note: no onion = 152.38" in context
    assert "Subtotal 152.38, GST 7.62, Total 160.0" in context
    assert "Order so far: empty" not in context


def test_the_cart_uses_the_same_clean_names_as_the_tools() -> None:
    ctx, server, tools = make_order_tools()
    server.next_name = "McAloo Tikki Burger ®"
    tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    context = build_context(NOW, ctx.order, Caller())
    assert "1 x McAloo Tikki Burger =" in context and "®" not in context


def test_meal_size_and_choices_are_part_of_the_line() -> None:
    ctx, _, tools = make_order_tools()
    body = {"dish_id": 4, "meal_size": "Medium", "options": [{"name": "Complimentary Ketchup"}]}
    assert tools.dispatch("add_to_order", body, ctx).ok
    assert "Medium meal" in build_context(NOW, ctx.order, Caller())


def test_a_draft_with_no_lines_reads_as_empty() -> None:
    ctx, _, tools = make_order_tools()
    tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    tools.dispatch("remove_from_order", {"line_id": 10}, ctx)
    assert "Order so far: empty" in build_context(NOW, ctx.order, Caller())


def test_a_known_customer_is_named_without_the_number() -> None:
    context = build_context(NOW, ActiveOrder(), Caller(ASHA))
    assert "Customer: Asha Rao" in context and "9876543210" not in context
    nameless = ASHA.model_copy(update={"name": None})
    assert "Customer: identified, no name given" in build_context(
        NOW, ActiveOrder(), Caller(nameless)
    )


def test_the_summary_of_earlier_turns_comes_last() -> None:
    context = build_context(NOW, ActiveOrder(), Caller(), "Earlier turns: T1 asked")
    assert context.endswith("Earlier turns: T1 asked")


def test_voice_rules_come_last_in_the_context_of_spoken_turns_only() -> None:
    assert VOICE_PROMPT not in build_context(NOW, ActiveOrder(), Caller())
    spoken = build_context(NOW, ActiveOrder(), Caller(), "Earlier turns: T1 asked", spoken=True)
    assert spoken.endswith(f"Earlier turns: T1 asked\n{VOICE_PROMPT}")


def test_the_system_message_has_no_voice_rules() -> None:
    assert system_prompt() == STABLE_PROMPT
    assert VOICE_PROMPT not in system_prompt("burgers: McVeggie")


def test_the_rules_tell_the_model_to_name_the_options_it_offers() -> None:
    # The customer cannot see tool results, least of all on a call: "one of these" is useless.
    assert "name the options in that same reply" in STABLE_PROMPT
    assert "cannot see your tool results" in STABLE_PROMPT


def test_usual_dishes_show_only_for_an_identified_customer() -> None:
    context = build_context(NOW, ActiveOrder(), Caller(ASHA, ["McSpicy Chicken", "Fries"]))
    assert "Usually orders: McSpicy Chicken, Fries" in context
    assert "Usually" not in build_context(NOW, ActiveOrder(), Caller())


def test_needs_line_joins_the_allergies_on_file_with_those_said_this_chat() -> None:
    plain = build_context(NOW, ActiveOrder(), Caller())
    assert "Needs" not in plain and "Allergies" not in plain
    saved = ASHA.model_copy(update={"preferences": {"allergies": ["milk", "soy"]}})
    assert "Needs: allergic to milk, soy" in build_context(NOW, ActiveOrder(), Caller(saved))
    caller = Caller(saved)
    caller.needs.add(["soy", "egg"], veg_only=True)
    context = build_context(NOW, ActiveOrder(), caller)
    assert "Needs: allergic to milk, soy, egg; vegetarian only" in context
    only_veg = Caller()
    only_veg.needs.add([], veg_only=True)
    assert "Needs: vegetarian only" in build_context(NOW, ActiveOrder(), only_veg)


def test_a_single_allergy_saved_as_a_word_is_still_read() -> None:
    saved = ASHA.model_copy(update={"preferences": {"allergies": "gluten"}})
    assert Caller(saved).allergies == ["gluten"] and Caller().allergies == []


def test_a_placed_order_says_it_was_placed_and_its_number() -> None:
    ctx, _, tools = make_order_tools()
    tools.dispatch("add_to_order", {"dish_id": 4}, ctx)
    assert "Order PLACED" not in build_context(NOW, ctx.order, Caller())
    tools.dispatch("place_order", {}, ctx)
    assert "Order PLACED as number 14" in build_context(NOW, ctx.order, Caller())
