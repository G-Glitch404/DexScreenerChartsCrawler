import psutil
import httpx
import asyncio

from pathlib import Path
from urllib.parse import quote, urlencode
from typing import AsyncGenerator, Optional, Any

from seleniumbase import Driver
from selenium.common.exceptions import InvalidSessionIdException, NoSuchWindowException
from urllib3.exceptions import ReadTimeoutError

from src.core.logger import Logger
from src.crawler.chart_parser import parse_dexscreener_bars
from src.items.candle import Candle
from src.items.pair import Pair
from src.util.utils import ROUTES


class DexscreenerCrawler:
    _logger = Logger('DexscreenerCrawler')
    client = httpx.AsyncClient()

    def __init__(self, proxy: dict = None):
        self.clean_processes()

        self._driver = None
        self.proxy: dict = proxy

        self._logger.info('Dexscreener Crawler completed initialization')

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.driver.quit()
        self.clean_processes()

    @property
    def driver(self):
        """ Returns the seleniumbase uc driver """
        if self._driver is None or not self._driver.is_connected():
            self.clean_processes()
            self._driver = Driver(
                uc=True,
                headless2=True,
                proxy=self.proxy,
                browser="chrome",
                binary_location="/usr/bin/chromium",
                dark_mode=True,
                do_not_track=True,
                disable_gpu=True,
                no_sandbox=True,
                page_load_strategy="eager",
                chromium_arg="--disable-dev-shm-usage, --disable-gpu, --no-sandbox",
            )
            self._logger.info("crawler cleaned browser process and restarted seleniumbase uc driver")

        return self._driver

    @staticmethod
    def _generate_chart_url(
        pair: Pair,
        cs: Optional[str] = None,
        ats: Optional[str] = None,
        abn: Optional[str] = None
    ) -> str:
        """ Generate a DexScreener chart endpoint from a resolved pair """
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

        if cs is not None: params["cs"] = str(cs)
        if ats is not None: params["ats"] = str(ats)
        if abn is not None: params["abn"] = str(abn)

        return (
            f"https://io.dexscreener.com/dex/chart/amm/v3/"
            f"{encoded_route}/bars/{encoded_chain}/"
            f"{encoded_pair_address}?{urlencode(params)}"
        )

    def clean_processes(self) -> None:
        for process in psutil.process_iter():
            try:
                proc_name: str = process.name().lower()
                if not any(["chromedriver" in proc_name, "chrome" in proc_name, "uc_driver" in proc_name]): continue
                process.kill()
                process.wait(1)
            except (psutil.NoSuchProcess, psutil.AccessDenied, ProcessLookupError) as e:
                try: self._logger.error(f"Couldn't close browser process error: {str(e)}")
                except AttributeError: pass

        self._driver = None

    async def _request(self, chart_url: str) -> bytes:
        """ request the charts url and return the response bytes for parsing """
        try: self.driver.get(chart_url)
        except (InvalidSessionIdException, NoSuchWindowException, ReadTimeoutError, TimeoutError) as e:
            raise Exception(f"Seleniumbase failed to open the chart_url {chart_url} - e: {e}")

        await asyncio.sleep(10)

        response = await self.client.get(
            self.driver.get_current_url(),
            timeout=30,
            headers={
                "User-Agent": self.driver.execute_script(
                    "return navigator.userAgent"
                ),
                "Referer": "https://dexscreener.com/",
                "Accept": "*/*",
            },
        )

        response.raise_for_status()

        return response.content

    async def crawl_charts(self, pair: Pair) -> AsyncGenerator[Candle, None]:
        """ Request the pair chart and parse its binary response """
        url: str = self._generate_chart_url(pair)
        response: bytes = await self._request(url)
        for candle in parse_dexscreener_bars(response):
            yield candle


async def run():
    """ test run the crawler """
    crawler = DexscreenerCrawler()

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


if __name__ == '__main__':
    asyncio.run(run())
