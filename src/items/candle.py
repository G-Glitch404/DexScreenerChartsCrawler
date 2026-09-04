from pydantic import BaseModel, ConfigDict


class Candle(BaseModel):
    """
    Represent a normalized DexScreener OHLCV candle

    Args:
        timestamp (int): Candle timestamp in milliseconds
        datetime (str): Candle timestamp as an ISO 8601 UTC string
        open (float): Opening token price
        open_usd (float): Opening token price in USD
        high (float): Highest token price
        high_usd (float): Highest token price in USD
        low (float): Lowest token price
        low_usd (float): Lowest token price in USD
        close (float): Closing token price
        close_usd (float): Closing token price in USD
        volume_usd (float): Candle trading volume in USD

    Returns:
        Candle: Normalized OHLCV candle model
    """

    model_config = ConfigDict(extra="forbid")

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
