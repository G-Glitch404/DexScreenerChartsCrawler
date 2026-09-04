from pydantic import BaseModel


class Candle(BaseModel):
    """ Normalized DexScreener OHLCV candle """
    timestamp: int
    datetime: str
    open: float
    open_usd: float
    high: float
    high_usd: float
    low: float
    low_usd: float
    close: float
    close_usd: float
    volume_usd: float


class Pair(BaseModel):
    """ needed data for requesting charts from dexscreener for a pair token """
    chain_id: str
    dex_id: str
    pair_address: str
    quote_token_address: str
    candles_amount: int = 329
    charts_resolution: int = 5
