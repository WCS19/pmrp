"""Typed canonical identifier definitions."""

from __future__ import annotations

import re
from typing import Any, ClassVar, Self

from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema

MAX_IDENTIFIER_LENGTH = 128
IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9]*_[a-z0-9][a-z0-9_-]*$")


class CanonicalIdentifier(str):
    """Opaque canonical identifier with a stable prefix and safe character set."""

    prefix: ClassVar[str]
    max_length: ClassVar[int] = MAX_IDENTIFIER_LENGTH

    def __new__(cls, value: str) -> Self:
        validated = cls.validate(value)
        return str.__new__(cls, validated)

    @classmethod
    def validate(cls, value: object) -> str:
        if type(value) is not str:
            msg = f"{cls.__name__} must be a string"
            raise TypeError(msg)
        if value == "":
            msg = f"{cls.__name__} must not be empty"
            raise ValueError(msg)
        if len(value) > cls.max_length:
            msg = f"{cls.__name__} must be at most {cls.max_length} characters"
            raise ValueError(msg)
        if not value.startswith(cls.prefix):
            msg = f"{cls.__name__} must start with {cls.prefix!r}"
            raise ValueError(msg)
        if IDENTIFIER_PATTERN.fullmatch(value) is None:
            msg = f"{cls.__name__} contains unsupported characters"
            raise ValueError(msg)
        return value

    @classmethod
    def _validate_pydantic(cls, value: str) -> Self:
        return cls(value)

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: Any,
        handler: GetCoreSchemaHandler,
    ) -> core_schema.CoreSchema:
        return core_schema.no_info_after_validator_function(
            cls._validate_pydantic,
            core_schema.str_schema(strict=True),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema_value: core_schema.CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        schema = handler(core_schema.str_schema())
        schema.update(
            {
                "maxLength": cls.max_length,
                "pattern": IDENTIFIER_PATTERN.pattern,
                "type": "string",
            }
        )
        return schema


class EventId(CanonicalIdentifier):
    prefix = "evt_"


class CommandId(CanonicalIdentifier):
    prefix = "cmd_"


class CorrelationId(CanonicalIdentifier):
    prefix = "corr_"


class CausationId(CanonicalIdentifier):
    prefix = "cause_"


class TraceId(CanonicalIdentifier):
    prefix = "trace_"


class ExchangeId(CanonicalIdentifier):
    prefix = "xchg_"


class AccountId(CanonicalIdentifier):
    prefix = "acct_"


class MarketId(CanonicalIdentifier):
    prefix = "mkt_"


class OutcomeId(CanonicalIdentifier):
    prefix = "out_"


class ContractId(CanonicalIdentifier):
    prefix = "ctr_"


class OrderId(CanonicalIdentifier):
    prefix = "ord_"


class FillId(CanonicalIdentifier):
    prefix = "fill_"


class PositionId(CanonicalIdentifier):
    prefix = "pos_"


class StrategyId(CanonicalIdentifier):
    prefix = "strat_"


class SignalId(CanonicalIdentifier):
    prefix = "sig_"


class IntentId(CanonicalIdentifier):
    prefix = "intent_"


class RiskDecisionId(CanonicalIdentifier):
    prefix = "risk_"


class ReplaySessionId(CanonicalIdentifier):
    prefix = "rpl_"


class SimulationSessionId(CanonicalIdentifier):
    prefix = "sim_"


class ExperimentId(CanonicalIdentifier):
    prefix = "exp_"


class ModelId(CanonicalIdentifier):
    prefix = "mdl_"


class FeatureSnapshotId(CanonicalIdentifier):
    prefix = "feat_"


class RelationshipId(CanonicalIdentifier):
    prefix = "rel_"


class SettlementId(CanonicalIdentifier):
    prefix = "set_"


SUPPORTED_IDENTIFIER_PREFIXES: tuple[str, ...] = (
    EventId.prefix,
    CommandId.prefix,
    CorrelationId.prefix,
    CausationId.prefix,
    TraceId.prefix,
    ExchangeId.prefix,
    AccountId.prefix,
    MarketId.prefix,
    OutcomeId.prefix,
    ContractId.prefix,
    OrderId.prefix,
    FillId.prefix,
    PositionId.prefix,
    StrategyId.prefix,
    SignalId.prefix,
    IntentId.prefix,
    RiskDecisionId.prefix,
    ReplaySessionId.prefix,
    SimulationSessionId.prefix,
    ExperimentId.prefix,
    ModelId.prefix,
    FeatureSnapshotId.prefix,
    RelationshipId.prefix,
    SettlementId.prefix,
)
