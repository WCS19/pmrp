import pytest

import pmrp

pytestmark = pytest.mark.unit


def test_package_exposes_version() -> None:
    assert pmrp.__version__ == "0.1.0"
