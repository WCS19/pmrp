from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.schemas.serialization import canonical_json, canonical_sha256

pytestmark = pytest.mark.property


@given(
    items=st.dictionaries(
        keys=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=8),
        values=st.decimals(
            allow_infinity=False,
            allow_nan=False,
            min_value=Decimal("-1000"),
            max_value=Decimal("1000"),
            places=4,
        ),
        min_size=1,
        max_size=12,
    )
)
def test_canonical_hash_is_stable_across_mapping_insertion_order(
    items: dict[str, Decimal],
) -> None:
    reversed_items = dict(reversed(tuple(items.items())))

    assert canonical_json(items) == canonical_json(reversed_items)
    assert canonical_sha256(items) == canonical_sha256(reversed_items)


@given(value=st.decimals(allow_infinity=False, allow_nan=False, places=8))
def test_decimal_serialization_uses_exact_decimal_string(value: Decimal) -> None:
    assert canonical_json({"value": value}) == f'{{"value":"{value}"}}'
