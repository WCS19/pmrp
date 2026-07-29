"""Shared SQLAlchemy declarative base for storage row models."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s__%(column_0_N_name)s",
    "uq": "uq_%(table_name)s__%(column_0_N_name)s",
    "ck": "ck_%(table_name)s__%(constraint_name)s",
    "fk": "fk_%(table_name)s__%(column_0_N_name)s__%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class StorageBase(DeclarativeBase):
    """Base class for SQLAlchemy 2 typed storage row models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
