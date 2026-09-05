import asyncio

import cloudscraper

from typing import Any, AsyncGenerator, Optional
from urllib.parse import quote, urlencode

from src.crawler.chart_parser import parse_dexscreener_bars
from src.items.candle import Candle
from src.items.pair import Pair
from src.util.utils import ROUTES


class DexscreenerCrawler:
    def __init__(self, proxy: Optional[dict[str, str]] = None):
        self.proxy = proxy
        self.client = cloudscraper.create_scraper(browser="chrome")

        if self.proxy:
            self.client.proxies.update(self.proxy)

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def close(self) -> None:
        """ Close the DexScreener HTTP session """
        self.client.close()

    @staticmethod
    def _generate_chart_url(
        pair: Pair,
        cs: Optional[str] = None,
        ats: Optional[str] = None,
        abn: Optional[str] = None,
    ) -> str:
        """
        Generate a DexScreener chart endpoint from a resolved pair

        Args:
            pair: Resolved trading pair containing chart request parameters
            cs: Optional chart parameter
            ats: Optional chart parameter
            abn: Optional chart parameter

        Returns:
            Fully encoded DexScreener chart endpoint URL

        Raises:
            ValueError: If the chain and DEX combination is unsupported
        """
        chain: str = str(pair.chain_id).strip().lower()
        dex: str = str(pair.dex_id).strip().lower()
        pair_address: str = str(pair.pair_address).strip()

        route: str = ROUTES.get((chain, dex))
        if not route:
            raise ValueError(f"unsupported chart route: {chain}/{dex}")

        encoded_route = quote(route, safe="")
        encoded_chain = quote(chain, safe="")
        encoded_pair_address = quote(pair_address, safe="")

        params: dict[str, Any] = {
            "mc": 1,
            "res": pair.charts_resolution,
            "cb": pair.candles_amount,
            "q": pair.quote_token_address,
            "uo": 0,
        }

        if cs is not None:
            params["cs"] = str(cs)

        if ats is not None:
            params["ats"] = str(ats)

        if abn is not None:
            params["abn"] = str(abn)

        return (
            "https://io.dexscreener.com/dex/chart/amm/v3/"
            f"{encoded_route}/bars/{encoded_chain}/"
            f"{encoded_pair_address}?{urlencode(params)}"
        )

    async def _request(self, chart_url: str) -> bytes:
        """
        Request a DexScreener chart URL and return its raw response bytes

        Args:
            chart_url: Fully generated DexScreener chart endpoint URL

        Returns:
            Raw binary chart response

        Raises:
            RuntimeError: If the DexScreener request fails
        """
        try:
            response = await asyncio.to_thread(
                self.client.get,
                chart_url,
                timeout=30,
                headers={
                    "Referer": "https://dexscreener.com/",
                    "Accept": "application/octet-stream",
                },
            )
            response.raise_for_status()
        except Exception as exc:
            raise RuntimeError(
                f"Failed to request DexScreener chart URL {chart_url}: {exc}"
            ) from exc

        return response.content

    async def crawl_charts(self, pair: Pair) -> AsyncGenerator[Candle, None]:
        """
        Request a pair chart and parse its binary candle response

        Args:
            pair: Resolved trading pair containing chart request parameters

        Yields:
            Parsed chart candles
        """
        url: str = self._generate_chart_url(pair)
        response: bytes = await self._request(url)

        for candle in parse_dexscreener_bars(response):
            yield candle


if __name__ == "__main__":
    async def run():
        """ Run a local DexScreener crawler test """
        crawler = DexscreenerCrawler()

        test_pair = Pair(
            chain_id="robinhood",
            dex_id="uniswap",
            pair_address="0x4be9657ec9002e528f4f17a5c43edc525a07f888f7b180c2afbf75e096c4f38a",
            quote_token_address="0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168",
            candles_amount=100,
            charts_resolution=5,
        )

        try:
            candles_counter: int = 0

            async for candle in crawler.crawl_charts(pair=test_pair):
                candles_counter += 1
                print(candle)

            print(candles_counter)
        finally:
            crawler.close()


    asyncio.run(run())
