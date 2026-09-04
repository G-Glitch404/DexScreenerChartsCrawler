from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from src.items.candle import Candle
from src.items.pair import Pair


class ChartRequest(BaseModel):
    """ Validate a chart crawling request """
    model_config = ConfigDict(extra="forbid")

    pair: Pair
    timeout_seconds: Optional[int] = Field(default=None, ge=10, le=600)
    proxy: Optional[dict[str, str]] = None


class ChartResponse(BaseModel):
    """ Represent a completed DexScreener chart crawl response """
    model_config = ConfigDict(extra="forbid")

    pair: Pair
    count: int = Field(ge=0)
    elapsed_ms: int = Field(ge=0)
    charts: list[Candle] = Field(default_factory=list)
