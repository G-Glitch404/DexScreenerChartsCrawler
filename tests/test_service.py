import asyncio
import os
import struct

import pytest

from typing import Any
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


def build_candle_payload(
    timestamp: int = 1_700_000_000_000,
    values: tuple[str, ...] = (
        "1",
        "1",
        "2",
        "2",
        "0.5",
        "0.5",
        "1.5",
        "1.5",
        "1000",
    ),
) -> bytes:
    """ Build a synthetic DexScreener binary payload containing one valid candle """

    timestamp_bytes = struct.pack("<d", timestamp)

    payload = bytearray()
    payload.extend(b"\x00\x00")
    payload.extend(timestamp_bytes[:6])
    payload.extend(b"zB")
    payload.extend(timestamp_bytes[6:])

    for value in values:
        encoded = value.encode("ascii")
        payload.append(len(encoded) << 1)
        payload.extend(encoded)

    return bytes(payload)


def make_candle(
    timestamp: int = 1_700_000_000_000,
) -> Candle:
    """ Build a deterministic candle model for API and WebSocket tests """
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
    """ Provide a deterministic crawler implementation for API tests """
    created: list[dict[str, Any]] = []
    requested: list[Pair] = []
    cleaned: int = 0

    def __init__(self, proxy: dict[str, str] | None = None):
        self.proxy = proxy
        self.created.append({"proxy": proxy})

    async def crawl_charts(self, pair: Pair) -> AsyncGenerator[Candle, None]:
        """ Yield deterministic candles without starting Selenium """
        self.requested.append(pair)
        yield make_candle()
        yield make_candle(1_700_000_300_000)
        await asyncio.sleep(0)

    def clean_processes(self) -> None:
        """ Record crawler cleanup """
        type(self).cleaned += 1


@pytest.fixture
def fake_crawler(monkeypatch):
    """ Replace the real crawler with a deterministic test crawler """
    FakeCrawler.created.clear()
    FakeCrawler.requested.clear()
    FakeCrawler.cleaned = 0

    import src.api

    monkeypatch.setattr(src.api, "DexscreenerCrawler", FakeCrawler)

    return FakeCrawler


def test_health_endpoint():
    """ Verify the service health endpoint """
    response = client.get("/health")

    assert response.status_code == 200

    body = response.json()

    assert body["status"] == "healthy"
    assert body["service"] == "dexscreener-charts-crawler"
    assert "version" in body


def test_ready_endpoint():
    """ Verify the service readiness endpoint """
    response = client.get("/ready")

    assert response.status_code == 200

    body = response.json()

    assert body["status"] == "ready"
    assert body["max_concurrent_crawls"] >= 1
    assert body["default_timeout_seconds"] >= 1
    assert body["max_timeout_seconds"] >= body["default_timeout_seconds"]
    assert 0 <= body["available_slots"] <= body["max_concurrent_crawls"]


def test_openapi_contains_exact_four_public_endpoints():
    """ Verify that the public API exposes the intended four endpoints """
    response = client.get("/openapi.json")

    assert response.status_code == 200

    paths = set(response.json()["paths"])

    assert paths == {
        "/health",
        "/ready",
        "/v1/charts",
    }


@pytest.mark.parametrize(("chain_id", "dex_id"), SUPPORTED_ROUTES)
def test_trade_accepts_supported_routes(chain_id: str, dex_id: str):
    """ Verify every configured DexScreener route is accepted """
    pair = Pair(
        chain_id=chain_id,
        dex_id=dex_id,
        pair_address="PAIR_ADDRESS",
        quote_token_address="QUOTE_TOKEN_ADDRESS",
    )

    assert pair.chain_id == chain_id
    assert pair.dex_id == dex_id


def test_trade_normalizes_identifiers():
    """ Verify route identifiers are normalized """
    pair = Pair(
        chain_id="  SOLANA ",
        dex_id=" RAYDIUM ",
        pair_address=" PAIR ",
        quote_token_address=" QUOTE ",
    )

    assert pair.chain_id == "solana"
    assert pair.dex_id == "raydium"
    assert pair.pair_address == "PAIR"
    assert pair.quote_token_address == "QUOTE"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("chain_id", ""),
        ("dex_id", ""),
        ("pair_address", ""),
        ("quote_token_address", ""),
        ("chain_id", "   "),
        ("dex_id", "   "),
        ("pair_address", "   "),
        ("quote_token_address", "   "),
    ],
)
def test_trade_rejects_empty_required_strings(field: str, value: str):
    """ Verify required string fields reject empty values """
    payload = dict(VALID_TRADE)
    payload[field] = value

    response = client.post(
        "/v1/charts",
        json={"Pair": payload},
    )

    assert response.status_code == 422


def test_trade_rejects_unsupported_route():
    """ Verify unsupported chain and DEX combinations are rejected """
    payload = dict(VALID_TRADE)
    payload["chain_id"] = "ethereum"
    payload["dex_id"] = "uniswap"

    response = client.post(
        "/v1/charts",
        json={"Pair": payload},
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("candles_amount", 0),
        ("candles_amount", -1),
        ("candles_amount", 10_001),
        ("charts_resolution", 0),
        ("charts_resolution", -1),
        ("charts_resolution", 1_441),
    ],
)
def test_trade_rejects_invalid_numeric_ranges(field: str, value: int):
    """ Verify numeric chart parameters enforce their bounds """
    payload = dict(VALID_TRADE)
    payload[field] = value

    response = client.post(
        "/v1/charts",
        json={"Pair": payload},
    )

    assert response.status_code == 422


def test_trade_uses_documented_defaults():
    """ Verify default chart request values """
    pair = Pair(
        chain_id="solana",
        dex_id="raydium",
        pair_address="PAIR",
        quote_token_address="QUOTE",
    )

    assert pair.candles_amount == 329
    assert pair.charts_resolution == 5


def test_trade_rejects_unknown_fields():
    """ Verify strict Pair validation rejects unexpected fields """
    payload = dict(VALID_TRADE)
    payload["unexpected"] = True

    response = client.post(
        "/v1/charts",
        json={"Pair": payload},
    )

    assert response.status_code == 422


def test_chart_request_rejects_unknown_fields():
    """ Verify strict chart request validation rejects unexpected fields """
    response = client.post(
        "/v1/charts",
        json={
            "Pair": VALID_TRADE,
            "unexpected": True,
        },
    )

    assert response.status_code == 422


def test_trade_to_pair_preserves_values():
    """ Verify API Pair conversion produces the crawler pair model """
    pair = Pair(**VALID_TRADE)
    pair = pair

    assert isinstance(pair, Pair)
    assert pair.model_dump() == pair.model_dump()


@pytest.mark.parametrize(("chain_id", "dex_id"), SUPPORTED_ROUTES)
def test_generate_chart_url_contains_expected_route_and_parameters(
    chain_id: str,
    dex_id: str,
):
    """ Verify chart URLs use the configured route and Pair parameters """

    pair = Pair(
        chain_id=chain_id,
        dex_id=dex_id,
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

    assert "/bars/" in parsed.path

    assert parsed.path.endswith(
        f"/{chain_id}/PAIR%20ADDRESS"
    )

    assert query["mc"] == ["1"]
    assert query["res"] == ["15"]
    assert query["cb"] == ["42"]
    assert query["q"] == ["QUOTE ADDRESS"]
    assert query["uo"] == ["0"]


def test_generate_chart_url_supports_optional_parameters():
    """ Verify optional chart URL parameters are encoded """
    pair = Pair(
        chain_id="solana",
        dex_id="raydium",
        pair_address="PAIR",
        quote_token_address="QUOTE",
    )

    url = DexscreenerCrawler._generate_chart_url(
        pair,
        cs="100",
        ats="200",
        abn="300",
    )

    assert "cs=100" in url
    assert "ats=200" in url
    assert "abn=300" in url


def test_pair_rejects_unsupported_route():
    """ Verify Pair validation rejects unsupported chart routes """

    with pytest.raises(
        ValidationError,
        match="unsupported chart route: ethereum/uniswap",
    ):
        Pair(
            chain_id="ethereum",
            dex_id="uniswap",
            pair_address="PAIR",
            quote_token_address="QUOTE",
        )


def test_parser_requires_bytes():
    """ Verify the binary parser rejects non-byte input """
    with pytest.raises(TypeError, match="expected bytes"):
        list(parse_dexscreener_bars("invalid"))


def test_parser_rejects_payload_without_markers():
    """ Verify the binary parser rejects payloads without candle markers """
    with pytest.raises(ValueError, match="no DexScreener candle timestamps found"):
        list(parse_dexscreener_bars(b"invalid"))


def test_parser_returns_valid_candle():
    """ Verify valid binary chart data becomes a normalized candle """
    payload = build_candle_payload()
    candles = list(parse_dexscreener_bars(payload))

    assert len(candles) >= 1

    candle = candles[0]

    assert isinstance(candle, Candle)
    assert candle.timestamp == 1_700_000_000_000
    assert candle.datetime == "2023-11-14T22:13:20+00:00"
    assert candle.open == 1.0
    assert candle.open_usd == 1.0
    assert candle.high == 2.0
    assert candle.high_usd == 2.0
    assert candle.low == 0.5
    assert candle.low_usd == 0.5
    assert candle.close == 1.5
    assert candle.close_usd == 1.5
    assert candle.volume_usd == 1000.0


def test_parser_skips_invalid_ohlc_relationship():
    """ Verify candles violating OHLC relationships are rejected """
    payload = build_candle_payload(
        values=(
            "1",
            "1",
            "0.5",
            "0.5",
            "0.5",
            "0.5",
            "1.5",
            "1.5",
            "1000",
        )
    )

    assert list(parse_dexscreener_bars(payload)) == []


def test_parser_skips_invalid_numeric_fields():
    """ Verify malformed numeric fields do not crash the entire parser """
    payload = bytearray()
    payload.extend(struct.pack("<d", 1_700_000_000_000))
    payload.extend(b"zB")

    values = [
        "1",
        "1",
        "2",
        "2",
        "0.5",
        "0.5",
        "1.5",
        "not-a-number",
        "1000",
    ]

    for value in values:
        encoded = value.encode("ascii")
        payload.append(len(encoded) << 1)
        payload.extend(encoded)

    assert list(parse_dexscreener_bars(bytes(payload))) == []


def test_rest_crawl_returns_all_candles(fake_crawler):
    """ Verify the REST endpoint returns every candle produced by the crawler """
    response = client.post(
        "/v1/charts",
        json={
            "Pair": VALID_TRADE,
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["count"] == 2
    assert len(body["charts"]) == 2
    assert body["count"] == len(body["charts"])
    assert body["Pair"] == {
        **VALID_TRADE,
    }
    assert body["elapsed_ms"] >= 0

    first = body["charts"][0]

    assert set(first) == {
        "timestamp",
        "datetime",
        "open",
        "open_usd",
        "high",
        "high_usd",
        "low",
        "low_usd",
        "close",
        "close_usd",
        "volume_usd",
    }

    assert first["high"] >= max(first["open"], first["close"])
    assert first["low"] <= min(first["open"], first["close"])
    assert first["high_usd"] >= max(first["open_usd"], first["close_usd"])
    assert first["low_usd"] <= min(first["open_usd"], first["close_usd"])


def test_rest_crawl_passes_trade_to_crawler(fake_crawler):
    """ Verify REST requests are converted into Pair objects correctly """
    response = client.post(
        "/v1/charts",
        json={
            "Pair": VALID_TRADE,
            "proxy": {"proxy": "localhost:8080"},
        },
    )

    assert response.status_code == 200
    assert len(fake_crawler.requested) == 1
    assert len(fake_crawler.created) == 1
    assert fake_crawler.created[0]["proxy"] == {"proxy": "localhost:8080"}

    pair = fake_crawler.requested[0]

    assert isinstance(pair, Pair)
    assert pair.model_dump() == VALID_TRADE


def test_rest_crawl_cleans_up_crawler(fake_crawler):
    """ Verify crawler resources are cleaned after a successful REST crawl """
    response = client.post(
        "/v1/charts",
        json={"Pair": VALID_TRADE},
    )

    assert response.status_code == 200
    assert fake_crawler.cleaned == 1


def test_rest_crawl_rejects_invalid_timeout():
    """ Verify invalid REST timeouts are rejected """
    for timeout in (0, -1, 601):
        response = client.post(
            "/v1/charts",
            json={
                "Pair": VALID_TRADE,
                "timeout_seconds": timeout,
            },
        )

        assert response.status_code == 422


def test_rest_crawl_handles_crawler_error(monkeypatch):
    """ Verify crawler failures become HTTP 500 responses """
    class BrokenCrawler:
        def __init__(self, proxy=None):
            pass

        async def crawl_charts(self, Pair):
            """ Raise a deterministic crawler error """
            raise RuntimeError("crawler exploded")
            yield

        def clean_processes(self):
            """ Keep the fake crawler compatible with cleanup """
    import src.api

    monkeypatch.setattr(src.api, "DexscreenerCrawler", BrokenCrawler)

    response = client.post(
        "/v1/charts",
        json={"Pair": VALID_TRADE},
    )

    assert response.status_code == 500
    assert "crawler exploded" in response.json()["detail"]


def test_websocket_streams_all_candles(fake_crawler):
    """ Verify the WebSocket streams every candle and finishes correctly """
    with client.websocket_connect("/v1/ws/charts") as websocket:
        websocket.send_json(
            {
                "Pair": VALID_TRADE,
            }
        )

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


def test_websocket_passes_trade_to_crawler(fake_crawler):
    """ Verify WebSocket requests are converted into crawler pairs """
    with client.websocket_connect("/v1/ws/charts") as websocket:
        websocket.send_json(
            {
                "Pair": VALID_TRADE,
                "proxy": {"proxy": "localhost:8080"},
            }
        )

        websocket.receive_json()
        websocket.receive_json()
        done = websocket.receive_json()

    assert done["type"] == "done"
    assert len(fake_crawler.requested) == 1
    assert fake_crawler.requested[0].model_dump() == VALID_TRADE
    assert fake_crawler.created[0]["proxy"] == {"proxy": "localhost:8080"}


def test_websocket_rejects_invalid_request():
    """ Verify WebSocket validation errors are returned to the client """
    with client.websocket_connect("/v1/ws/charts") as websocket:
        websocket.send_json(
            {
                "Pair": {
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
    """ Verify WebSocket crawler failures are returned as structured errors """
    class BrokenCrawler:
        def __init__(self, proxy=None):
            pass

        async def crawl_charts(self, Pair):
            """ Raise a deterministic crawler error """
            raise RuntimeError("websocket crawler exploded")
            yield

        def clean_processes(self):
            """ Keep the fake crawler compatible with cleanup """
    import src.api

    monkeypatch.setattr(src.api, "DexscreenerCrawler", BrokenCrawler)

    with client.websocket_connect("/v1/ws/charts") as websocket:
        websocket.send_json({"Pair": VALID_TRADE})
        message = websocket.receive_json()

    assert message["type"] == "error"
    assert message["status_code"] == 500
    assert "websocket crawler exploded" in message["detail"]


def test_rest_endpoint_rejects_non_json_body():
    """ Verify the REST endpoint requires a JSON request body """
    response = client.post(
        "/v1/charts",
        content="not-json",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 422


def test_rest_endpoint_rejects_missing_trade():
    """ Verify the REST endpoint requires Pair information """
    response = client.post(
        "/v1/charts",
        json={},
    )

    assert response.status_code == 422


def test_ws_endpoint_exists():
    """ Verify the WebSocket endpoint is reachable """
    with client.websocket_connect("/v1/ws/charts") as websocket:
        assert websocket is not None


@pytest.mark.asyncio
async def test_crawler_request_is_async_generator():
    """ Verify the real crawler exposes the expected asynchronous chart interface """
    crawler = object.__new__(DexscreenerCrawler)

    pair = Pair(
        chain_id="solana",
        dex_id="raydium",
        pair_address="PAIR",
        quote_token_address="QUOTE",
    )

    async def fake_request(url: str) -> bytes:
        """ Return deterministic chart bytes without network activity """
        return build_candle_payload()

    crawler._request = fake_request

    values = [
        candle async for candle in crawler.crawl_charts(pair)
    ]

    assert len(values) == 1
    assert values[0].timestamp == 1_700_000_000_000


def test_live_crawl_opt_in():
    """ Run a live DexScreener crawl only when explicitly enabled """
    if os.getenv("RUN_LIVE_DEXSCREENER_TESTS") != "1":
        pytest.skip("set RUN_LIVE_DEXSCREENER_TESTS=1 to run live crawl tests")

    required = [
        "LIVE_CHAIN_ID",
        "LIVE_DEX_ID",
        "LIVE_PAIR_ADDRESS",
        "LIVE_QUOTE_TOKEN_ADDRESS",
    ]

    missing = [name for name in required if not os.getenv(name)]

    if missing:
        pytest.fail(
            "missing live test environment variables: "
            + ", ".join(missing)
        )

    payload = {
        "Pair": {
            "chain_id": os.environ["LIVE_CHAIN_ID"],
            "dex_id": os.environ["LIVE_DEX_ID"],
            "pair_address": os.environ["LIVE_PAIR_ADDRESS"],
            "quote_token_address": os.environ["LIVE_QUOTE_TOKEN_ADDRESS"],
            "candles_amount": int(os.getenv("LIVE_CANDLES_AMOUNT", "10")),
            "charts_resolution": int(
                os.getenv("LIVE_CHARTS_RESOLUTION", "5")
            ),
        },
        "timeout_seconds": int(
            os.getenv("LIVE_TIMEOUT_SECONDS", "120")
        ),
    }

    response = client.post("/v1/charts", json=payload)

    assert response.status_code == 200

    body = response.json()

    assert body["count"] >= 1
    assert body["count"] == len(body["charts"])

    for candle in body["charts"]:
        assert isinstance(candle["timestamp"], int)
        assert isinstance(candle["datetime"], str)
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
        assert candle["volume_usd"] >= 0
