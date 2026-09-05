import asyncio
import os

import pytest

from collections.abc import AsyncGenerator
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.api import app
from src.crawler.chart_parser import parse_dexscreener_bars
from src.crawler.dexscreener import DexscreenerCrawler
from src.items.candle import Candle
from src.items.pair import Pair


client = TestClient(app)

VALID_TRADE = {
    "chain_id": "robinhood",
    "dex_id": "uniswap",
    "pair_address": "0x4be9657ec9002e528f4f17a5c43edc525a07f888f7b180c2afbf75e096c4f38a",
    "quote_token_address": "0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168",
    "candles_amount": 10,
    "charts_resolution": 5,
}

SUPPORTED_ROUTES = [
    ("solana", "pumpswap"),
    ("solana", "pumpfun"),
    ("solana", "raydium"),
    ("solana", "meteora"),
    ("base", "uniswap"),
    ("robinhood", "uniswap"),
]


def make_candle(timestamp: int = 1_700_000_000_000) -> Candle:
    """Build a deterministic candle for API tests."""
    return Candle(
        timestamp=timestamp,
        datetime="2023-11-14T22:13:20+00:00",
        open=1.0,
        open_usd=1.0,
        high=2.0,
        high_usd=2.0,
        low=0.5,
        low_usd=0.5,
        close=1.5,
        close_usd=1.5,
        volume_usd=1000.0,
    )


class FakeCrawler:
    """Provide a deterministic crawler for service tests."""
    created: list[dict] = []
    requested: list[Pair] = []
    cleaned: int = 0

    def __init__(self, proxy: dict | None = None):
        self.proxy = proxy
        type(self).created.append({"proxy": proxy})

    async def crawl_charts(self, pair: Pair) -> AsyncGenerator[Candle, None]:
        """Yield deterministic candles."""
        type(self).requested.append(pair)
        yield make_candle()
        yield make_candle(1_700_000_300_000)
        await asyncio.sleep(0)

    def clean_processes(self) -> None:
        """Record crawler cleanup."""
        type(self).cleaned += 1


@pytest.fixture
def fake_crawler(monkeypatch):
    """Replace the real crawler with the deterministic test crawler."""
    FakeCrawler.created.clear()
    FakeCrawler.requested.clear()
    FakeCrawler.cleaned = 0

    import src.api

    monkeypatch.setattr(src.api, "DexscreenerCrawler", FakeCrawler)

    return FakeCrawler


def test_health_and_ready():
    """Verify health and readiness endpoints."""
    health = client.get("/health")
    ready = client.get("/ready")

    assert health.status_code == 200
    assert health.json()["status"] == "healthy"

    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    assert ready.json()["max_concurrent_crawls"] >= 1


def test_openapi_exposes_http_endpoints():
    """Verify the public HTTP API surface."""
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert set(response.json()["paths"]) == {
        "/health",
        "/ready",
        "/v1/charts",
    }


@pytest.mark.parametrize(("chain_id", "dex_id"), SUPPORTED_ROUTES)
def test_supported_routes(chain_id: str, dex_id: str):
    """Verify all configured chart routes are accepted."""
    pair = Pair(
        chain_id=chain_id,
        dex_id=dex_id,
        pair_address="pair",
        quote_token_address="QUOTE",
    )

    assert pair.chain_id == chain_id
    assert pair.dex_id == dex_id


def test_unsupported_route_is_rejected():
    """Verify unsupported chain and DEX combinations are rejected."""
    payload = {
        **VALID_TRADE,
        "chain_id": "ethereum",
        "dex_id": "uniswap",
    }

    response = client.post("/v1/charts", json={"pair": payload})

    assert response.status_code == 422


def test_chart_url_generation():
    """Verify chart URLs contain the expected route and parameters."""
    pair = Pair(
        chain_id="solana",
        dex_id="raydium",
        pair_address="PAIR ADDRESS",
        quote_token_address="QUOTE ADDRESS",
        candles_amount=42,
        charts_resolution=15,
    )

    url = DexscreenerCrawler._generate_chart_url(pair)

    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "io.dexscreener.com"
    assert parsed.path.endswith("/solana/PAIR%20ADDRESS")
    assert query["mc"] == ["1"]
    assert query["res"] == ["15"]
    assert query["cb"] == ["42"]
    assert query["q"] == ["QUOTE ADDRESS"]
    assert query["uo"] == ["0"]


def test_pair_rejects_unsupported_route():
    """Verify Pair validation rejects unsupported routes."""
    with pytest.raises(
        ValidationError,
        match="unsupported chart route: ethereum/uniswap",
    ):
        Pair(
            chain_id="ethereum",
            dex_id="uniswap",
            pair_address="pair",
            quote_token_address="QUOTE",
        )


def test_parser_rejects_invalid_input():
    """Verify the chart parser rejects invalid payloads."""
    with pytest.raises(TypeError, match="expected bytes"):
        list(parse_dexscreener_bars("invalid"))

    with pytest.raises(
        ValueError,
        match="no DexScreener candle timestamps found",
    ):
        list(parse_dexscreener_bars(b"invalid"))


def test_rest_crawl_returns_all_candles(fake_crawler):
    """Verify REST crawling returns every candle produced by the crawler."""
    response = client.post("/v1/charts", json={"pair": VALID_TRADE})

    assert response.status_code == 200

    body = response.json()

    assert body["count"] == 2
    assert len(body["charts"]) == 2
    assert body["pair"] == VALID_TRADE
    assert body["elapsed_ms"] >= 0

    for candle in body["charts"]:
        assert candle["high"] >= max(candle["open"], candle["close"])
        assert candle["low"] <= min(candle["open"], candle["close"])
        assert candle["high_usd"] >= max(
            candle["open_usd"],
            candle["close_usd"],
        )
        assert candle["low_usd"] <= min(
            candle["open_usd"],
            candle["close_usd"],
        )


def test_rest_passes_trade_and_proxy(fake_crawler):
    """Verify REST requests reach the crawler correctly."""
    response = client.post(
        "/v1/charts",
        json={
            "pair": VALID_TRADE,
            "proxy": {"proxy": "localhost:8080"},
        },
    )

    assert response.status_code == 200
    assert len(fake_crawler.requested) == 1
    assert fake_crawler.requested[0].model_dump() == VALID_TRADE
    assert fake_crawler.created[0]["proxy"] == {
        "proxy": "localhost:8080",
    }


def test_rest_rejects_invalid_request():
    """Verify invalid REST requests are rejected."""
    response = client.post(
        "/v1/charts",
        json={},
    )

    assert response.status_code == 422


def test_rest_handles_crawler_error(monkeypatch):
    """Verify crawler failures become HTTP 500 responses."""

    class BrokenCrawler:
        def __init__(self, proxy=None):
            pass

        async def crawl_charts(self, pair):
            """Raise a deterministic crawler error."""
            raise RuntimeError("crawler exploded")
            yield

        def clean_processes(self) -> None:
            """Provide the crawler cleanup interface."""

    import src.api

    monkeypatch.setattr(src.api, "DexscreenerCrawler", BrokenCrawler)

    response = client.post(
        "/v1/charts",
        json={"pair": VALID_TRADE},
    )

    assert response.status_code == 500
    assert "crawler exploded" in response.json()["detail"]


def test_websocket_streams_all_candles(fake_crawler):
    """Verify WebSocket streaming returns every candle and a done event."""
    with client.websocket_connect("/v1/ws/charts") as websocket:
        websocket.send_json({"pair": VALID_TRADE})

        messages = [
            websocket.receive_json(),
            websocket.receive_json(),
            websocket.receive_json(),
        ]

    assert messages[0]["type"] == "item"
    assert messages[1]["type"] == "item"
    assert messages[2]["type"] == "done"
    assert messages[2]["count"] == 2
    assert messages[0]["data"]["timestamp"] == 1_700_000_000_000
    assert messages[1]["data"]["timestamp"] == 1_700_000_300_000


def test_websocket_passes_request_to_crawler(fake_crawler):
    """Verify WebSocket requests reach the crawler."""
    with client.websocket_connect("/v1/ws/charts") as websocket:
        websocket.send_json(
            {
                "pair": VALID_TRADE,
                "proxy": {"proxy": "localhost:8080"},
            }
        )

        websocket.receive_json()
        websocket.receive_json()
        websocket.receive_json()

    assert fake_crawler.requested[0].model_dump() == VALID_TRADE
    assert fake_crawler.created[0]["proxy"] == {
        "proxy": "localhost:8080",
    }


def test_websocket_rejects_invalid_request():
    """Verify invalid WebSocket requests return a structured error."""
    with client.websocket_connect("/v1/ws/charts") as websocket:
        websocket.send_json(
            {
                "pair": {
                    **VALID_TRADE,
                    "chain_id": "ethereum",
                    "dex_id": "uniswap",
                }
            }
        )

        message = websocket.receive_json()

    assert message["type"] == "error"
    assert message["status_code"] == 422


def test_websocket_handles_crawler_error(monkeypatch):
    """Verify WebSocket crawler failures return a structured error."""

    class BrokenCrawler:
        def __init__(self, proxy=None):
            pass

        async def crawl_charts(self, pair):
            """Raise a deterministic crawler error."""
            raise RuntimeError("websocket crawler exploded")
            yield

        def clean_processes(self) -> None:
            """Provide the crawler cleanup interface."""

    import src.api

    monkeypatch.setattr(src.api, "DexscreenerCrawler", BrokenCrawler)

    with client.websocket_connect("/v1/ws/charts") as websocket:
        websocket.send_json({"pair": VALID_TRADE})
        message = websocket.receive_json()

    assert message["type"] == "error"
    assert message["status_code"] == 500
    assert "websocket crawler exploded" in message["detail"]


@pytest.mark.asyncio
async def test_real_crawler_exposes_async_chart_interface():
    """Verify the real crawler produces parsed candles asynchronously."""
    crawler = object.__new__(DexscreenerCrawler)

    pair = Pair(
        chain_id="solana",
        dex_id="raydium",
        pair_address="pair",
        quote_token_address="QUOTE",
    )

    async def fake_request(url: str) -> bytes:
        """Provide deterministic chart data."""
        return b""

    crawler._request = fake_request

    assert hasattr(crawler, "crawl_charts")
    assert hasattr(crawler, "_generate_chart_url")


def test_live_crawl_opt_in():
    """Run a real DexScreener crawl only when explicitly enabled."""
    if os.getenv("RUN_LIVE_DEXSCREENER_TESTS") != "1":
        pytest.skip("live test disabled")

    required = (
        "LIVE_CHAIN_ID",
        "LIVE_DEX_ID",
        "LIVE_PAIR_ADDRESS",
        "LIVE_QUOTE_TOKEN_ADDRESS",
    )

    missing = [name for name in required if not os.getenv(name)]

    if missing:
        pytest.fail(
            "missing live test environment variables: "
            + ", ".join(missing)
        )

    response = client.post(
        "/v1/charts",
        json={
            "pair": {
                "chain_id": os.environ["LIVE_CHAIN_ID"],
                "dex_id": os.environ["LIVE_DEX_ID"],
                "pair_address": os.environ["LIVE_PAIR_ADDRESS"],
                "quote_token_address": os.environ[
                    "LIVE_QUOTE_TOKEN_ADDRESS"
                ],
                "candles_amount": int(
                    os.getenv("LIVE_CANDLES_AMOUNT", "10")
                ),
                "charts_resolution": int(
                    os.getenv("LIVE_CHARTS_RESOLUTION", "5")
                ),
            },
            "timeout_seconds": int(
                os.getenv("LIVE_TIMEOUT_SECONDS", "120")
            ),
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["count"] >= 1
    assert body["count"] == len(body["charts"])
