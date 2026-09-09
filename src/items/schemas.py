from typing import Optional, Union, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.items.candle import DexscreenerCandle
from src.items.pair import Pair, BirdeyePair


class ChartRequest(BaseModel):
    """ Validate a chart crawling request """
    model_config = ConfigDict(extra="forbid")

    pair: Union[Pair, BirdeyePair]
    crawler: Literal["dexscreener", "birdeye"]
    timeout_seconds: Optional[int] = Field(default=None, ge=10, le=600)
    proxy: Optional[dict[str, str]] = None


class ChartResponse(BaseModel):
    """ Represent a completed DexScreener chart crawl response """
    model_config = ConfigDict(extra="forbid")

    pair: Pair
    crawler: Literal["dexscreener", "birdeye"]
    count: int = Field(ge=0)
    elapsed_ms: int = Field(ge=0)
    charts: list[DexscreenerCandle] = Field(default_factory=list)
