import pytest
from pydantic import ValidationError

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.enums import ExchangeName, MarketStatus, Side

pytestmark = pytest.mark.unit


class EnumModel(CanonicalModel):
    exchange: ExchangeName
    side: Side
    status: MarketStatus


def test_enum_serialization_uses_stable_values() -> None:
    model = EnumModel(
        exchange=ExchangeName.KALSHI,
        side=Side.BUY,
        status=MarketStatus.OPEN,
    )

    assert model.model_dump(mode="json") == {
        "exchange": "kalshi",
        "side": "buy",
        "status": "open",
    }


def test_enum_json_round_trip_preserves_enum_members() -> None:
    model = EnumModel.model_validate_json(
        """
        {
          "exchange": "kalshi",
          "side": "sell",
          "status": "halted"
        }
        """
    )

    assert model.exchange is ExchangeName.KALSHI
    assert model.side is Side.SELL
    assert model.status is MarketStatus.HALTED


def test_unknown_enum_value_is_rejected() -> None:
    with pytest.raises(ValidationError, match="Input should be"):
        EnumModel.model_validate_json(
            """
            {
              "exchange": "unknown_exchange",
              "side": "buy",
              "status": "open"
            }
            """
        )
