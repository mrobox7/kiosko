"""The request printout plays its scripted order to the end on a menu it has not seen before."""

import json
from pathlib import Path

from tests.show_request import run
from tests.support.fake_order_server import PRODUCTS


def test_the_scripted_order_runs_to_the_end_on_a_saved_catalog(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"version": "v1", "products": list(PRODUCTS.values())}))
    calls = run(catalog)
    assert len(calls) == 10  # six messages: four tool calls and six answers
    last = calls[-1].messages
    assert last[-1].tool_outcomes[0].content.count("order_number") == 1  # the order was placed
    assert "Welcome" not in calls[0].system and "Menu:" in calls[0].system
