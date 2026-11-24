"""Generated Python code: importable and roundtrip-safe with pyfory.

Needs `scripts/ci/generate.sh python` first (tests/e2e/out/python).
"""

from __future__ import annotations

import datetime
import importlib
import pkgutil
import sys
from pathlib import Path
from typing import Any

import pytest

OUT = Path(__file__).resolve().parent.parent / "out" / "python"


@pytest.fixture(scope="module")
def modules() -> dict[str, Any]:
    if not OUT.is_dir():
        pytest.skip("tests/e2e/out/python missing; run scripts/ci/compile.sh python")
    pytest.importorskip("pyfory", reason="needs the e2e dependency group (uv run --group e2e)")
    sys.path.insert(0, str(OUT))
    names = [m.name for m in pkgutil.iter_modules([str(OUT)])]
    return {name: importlib.import_module(name) for name in names}


def test_all_generated_modules_import(modules: dict[str, Any]) -> None:
    assert sorted(modules) == ["demo_common", "demo_order", "demo_status"]


def sample_order(modules: dict[str, Any]) -> Any:
    o, c, s = modules["demo_order"], modules["demo_common"], modules["demo_status"]
    line = o.Order.Line(
        sku="A-1", price=c.Money(units=5, currency="EUR"), kind=o.Order.Line.Kind.ITEM, quantity=2
    )
    return o.Order(
        id="o1",
        lines=[line],
        totals={"net": c.Money(units=10, currency="EUR")},
        lines_by_pos={1: line},
        note="hi",
        status=s.Status.PAID,
        payment=o.Order.Payment.iban(o.Iban(country="DE", number="123")),
        created_at=datetime.datetime(2026, 11, 24, 12, 0, tzinfo=datetime.timezone.utc),
        ttl=datetime.timedelta(seconds=30),
        sequence=123456789,
        first_line=None,
        default_kind=o.Order.Line.Kind.FEE,
        tags=["a", "b"],
        blob=b"\x00\x01",
        ratio=0.5,
        score=1.5,
        urgent=True,
        delta=-3,
        big_delta=-4,
        f32=5,
        f64=6,
        sf32=-7,
        sf64=-8,
        u64=9,
        i32=10,
    )


@pytest.mark.roundtrip
def test_roundtrip(modules: dict[str, Any], pair: tuple[str, str]) -> None:
    if pair != ("python", "python"):
        pytest.skip(f"no cross-language runner for {pair[0]} -> {pair[1]} yet")
    order = sample_order(modules)
    data = order.to_bytes()
    assert type(order).from_bytes(data) == order


@pytest.mark.roundtrip
def test_ref_tracking_keeps_shared_objects(modules: dict[str, Any], pair: tuple[str, str]) -> None:
    if pair != ("python", "python"):
        pytest.skip(f"no cross-language runner for {pair[0]} -> {pair[1]} yet")
    o = modules["demo_order"]
    root = o.Tree(parent=None, children=[], named={})
    child = o.Tree(parent=None, children=[], named={})
    root.children = [child, child]  # (fory.field).ref = true on children
    back = o.Tree.from_bytes(root.to_bytes())
    assert back.children[0] is back.children[1]
