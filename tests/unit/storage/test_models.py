"""Tests for storage SQLAlchemy metadata."""

from __future__ import annotations

import pytest

from pmrp.storage.models import NAMING_CONVENTION, StorageBase


@pytest.mark.unit
def test_storage_base_uses_project_naming_convention() -> None:
    assert StorageBase.metadata.naming_convention == NAMING_CONVENTION
    assert NAMING_CONVENTION["pk"] == "pk_%(table_name)s"
    assert NAMING_CONVENTION["fk"] == (
        "fk_%(table_name)s__%(column_0_N_name)s__%(referred_table_name)s"
    )
