import os
import datetime as dt
from typing import AsyncGenerator, Optional

import httpx2

from src.items.candle import BirdeyeCandle
from src.items.pair import Pair


class BirdeyeCrawler:
    BASE_URL: str = "https://public-api.birdeye.so"
    INTERVALS: dict[int, str] = {1: "1m", 3: "3m", 5: "5m", 15: "15m", 30: "30m", 60: "1H", 120: "2H", 240: "4H", 360: "6H", 480: "8H", 720: "12H", 1440: "1D", 4320: "3D", 10080: "1W", 43200: "1M"}
    MAX_CANDLES: int = 5000

    def __init__(self, proxy: Optional[str] = None, api_key: Optional[str] = None, timeout: float = 30.0):
        """ Initialize the Birdeye crawler """
        self.api_key = (api_key or os.getenv("BIRDEYE_API_KEY", "")).strip()
        if not self.api_key:
            raise ValueError("BIRDEYE_API_KEY is required")

        self.client = httpx2.AsyncClient(base_url=self.BASE_URL, timeout=timeout, proxy=proxy)

    def _interval(self, resolution: int) -> str:
        """ Convert chart resolution to a Birdeye interval """
        try: return self.INTERVALS[int(resolution)]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"unsupported charts_resolution: {resolution}") from exc

    @staticmethod
    def _number(value) -> Optional[float]:
        """ Convert an API value to a finite float """
        try:
            value = float(value)
            return value if value == value and value not in (float("inf"), float("-inf")) else None
        except (TypeError, ValueError):
            return None

    @classmethod
    def _candle(cls, item: dict) -> Optional[BirdeyeCandle]:
        """ Normalize and validate a Birdeye OHLCV record """
        timestamp = cls._number(item.get("unixTime", item.get("unix_time", item.get("timestamp"))))
        open_price = cls._number(item.get("o", item.get("open")))
        high = cls._number(item.get("h", item.get("high")))
        low = cls._number(item.get("l", item.get("low")))
        close = cls._number(item.get("c", item.get("close")))
        volume_usd = cls._number(item.get("v_usd", item.get("volume_usd")))

        if any([
            None in (timestamp, open_price, high, low, close, volume_usd),
            timestamp <= 0,
            close <= 0,
            volume_usd < 0,
        ]): return None

        valid = high >= max(open_price, close) and low <= min(open_price, close)
        direction = "bullish" if close > open_price else "bearish" if close < open_price else "doji"

        return BirdeyeCandle(
            timestamp=int(timestamp * 1000),
            datetime=dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).isoformat(),
            ohlc_valid=valid,
            direction=direction,
            open=open_price,
            high=high,
            low=low,
            close=close,
            volume_usd=volume_usd,
        )

    async def crawl_charts(self, pair: Pair) -> AsyncGenerator[BirdeyeCandle, None]:
        """ Retrieve and yield Birdeye candles for a pair """
        amount = min(max(int(pair.candles_amount), 0), self.MAX_CANDLES)
        if not amount: return

        response = await self.client.get(
            "/defi/v3/ohlcv/pair",
            params={
                "address": str(pair.pair_address).strip(),
                "type": self._interval(pair.charts_resolution),
                "mode": "count",
                "count_limit": amount,
                "time_to": int(dt.datetime.now(dt.timezone.utc).timestamp()),
                "padding": "false",
                "outlier": "false",
            },
            headers={
                "X-API-KEY": self.api_key,
                "x-chain": str(pair.chain_id).strip().lower()
            },
        )

        if response.is_error:
            try: detail = response.json()
            except ValueError: detail = response.text
            raise RuntimeError(f"Birdeye HTTP {response.status_code}: {detail}")

        body = response.json()

        if body.get("success") is False:
            raise RuntimeError(
                body.get("message") or body.get("error") or f"Birdeye request failed: {body}"
            )

        for item in sorted(
            (item for item in body["data"]["items"]),
            key=lambda x: x["unix_time"]
        ):
            candle = self._candle(item)
            if candle: yield candle

    async def close(self) -> None:
        """ Close the HTTP client """
        await self.client.aclose()

    async def __aenter__(self):
        """ Enter the asynchronous crawler context """
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        """ Exit the asynchronous crawler context """
        await self.close()


if __name__ == "__main__":
    import asyncio

    async def run():
        """ Run a local Birdeye crawler test """
        crawler = BirdeyeCrawler()

        test_pair = Pair(
            chain_id="robinhood",
            dex_id="uniswap",
            pair_address="0x4be9657ec9002e528f4f17a5c43edc525a07f888f7b180c2afbf75e096c4f38a",
            quote_token_address="0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168",
            candles_amount=100,
            charts_resolution=5,
        )

        candles_counter: int = 0

        async for candle in crawler.crawl_charts(pair=test_pair):
            candles_counter += 1
            print(candle)

        print(candles_counter)


    asyncio.run(run())
