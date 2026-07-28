import string

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.schemas.identifiers import EventId

pytestmark = pytest.mark.property

_FIRST_SUFFIX_CHARACTER = tuple(string.ascii_lowercase + string.digits)
_REST_SUFFIX_CHARACTER = tuple(string.ascii_lowercase + string.digits + "_-")


@given(
    first=st.sampled_from(_FIRST_SUFFIX_CHARACTER),
    rest=st.text(alphabet=_REST_SUFFIX_CHARACTER, min_size=0, max_size=31),
)
def test_event_id_accepts_supported_identifier_suffixes(first: str, rest: str) -> None:
    value = EventId(f"evt_{first}{rest}")

    assert str(value) == f"evt_{first}{rest}"


@given(
    first=st.sampled_from(_FIRST_SUFFIX_CHARACTER),
    rest=st.text(alphabet=_REST_SUFFIX_CHARACTER, min_size=0, max_size=31),
)
def test_event_id_rejects_other_supported_prefixes(first: str, rest: str) -> None:
    with pytest.raises(ValueError, match="must start with 'evt_'"):
        EventId(f"cmd_{first}{rest}")
