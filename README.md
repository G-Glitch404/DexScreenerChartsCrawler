# DexScreener Charts Crawler

A FastAPI microservice for retrieving normalized OHLCV chart data from DexScreener's chart infrastructure.

The service is designed for applications that need historical token price candles without embedding DexScreener's binary chart parsing logic into the consuming application. It exposes a small HTTP/WebSocket API, validates chart requests with Pydantic, limits concurrent crawl operations, supports optional proxies, and converts DexScreener's binary chart response into a stable JSON candle format.

## What this service does

At a high level, a request follows this path:

```text
Client
  |
  | HTTP POST /v1/charts
  | or WebSocket /v1/ws/charts
  v
FastAPI API
  |
  | validate ChartRequest
  | enforce timeout + concurrency limits
  v
DexScreener crawler
  |
  | build DexScreener chart URL
  | request binary chart payload
  v
DexScreener chart endpoint
  |
  | binary response
  v
Binary chart parser
  |
  | decode timestamps + OHLCV values
  | validate OHLC relationships
  v
Normalized Candle objects
  |
  +--> JSON response
  +--> WebSocket item stream
```

The public service API is intentionally small:

| Method | Endpoint        | Purpose                                               |
|--------|-----------------|-------------------------------------------------------|
| `GET`  | `/health`       | Liveness check                                        |
| `GET`  | `/ready`        | Readiness/configuration check                         |
| `POST` | `/v1/charts`    | Crawl all parsed candles and return one JSON document |
| `WS`   | `/v1/ws/charts` | Crawl and stream candles incrementally                |

The service currently supports the chart routes configured in `src/util/utils.py`:

| Chain       | DexScreener DEX ID | Internal chart route |
|-------------|--------------------|----------------------|
| `solana`    | `pumpswap`         | `pumpfundex`         |
| `solana`    | `pumpfun`          | `pumpfundex`         |
| `solana`    | `raydium`          | `solamm`             |
| `solana`    | `meteora`          | `meteora`            |
| `base`      | `uniswap`          | `uniswapv4`          |
| `robinhood` | `uniswap`          | `uniswapv4`          |

An unsupported `chain_id` + `dex_id` combination is rejected with validation error `422`.

---

## Features

- FastAPI HTTP API with automatically generated OpenAPI documentation.
- WebSocket endpoint for incremental candle delivery.
- Normalized OHLCV candle schema.
- Configurable candle count and resolution.
- Configurable per-request timeout with service-wide maximum.
- Global concurrency gate to avoid unlimited simultaneous crawls.
- Optional HTTP/HTTPS proxy support per request.
- Binary DexScreener chart response parsing.
- OHLC consistency checks during parsing.
- Docker-ready deployment.
- `uv`-based Python dependency management.
- Pytest + pytest-asyncio development setup.

---

## Requirements

### Local development

- Python `3.12.x`
- `uv`
- Network access to DexScreener

The project declares Python `>=3.12,<3.13` and uses the following main dependencies:

- `fastapi`
- `uvicorn`
- `pydantic`
- `pydantic-settings`
- `cloudscraper`

Development dependencies include `pytest`, `pytest-asyncio`, and `httpx2`.

### Docker

The supplied Dockerfile is based on `python:3.12-slim-bookworm` and installs Chromium/Chromedriver plus the runtime dependencies required by the image.

---

## Running locally

Clone the repository and install the locked environment:

```bash
git clone https://github.com/G-Glitch404/DexScreenerChartsCrawler.git
cd DexScreenerChartsCrawler
uv sync --locked
```

Start the API:

```bash
uv run uvicorn src.api:app --host 0.0.0.0 --port 9098
```

The service listens on:

```text
http://127.0.0.1:9098
```

The API documentation is available at:

```text
http://127.0.0.1:9098/docs
http://127.0.0.1:9098/redoc
```

You can also start it through the package entry point:

```bash
uv run python -m src
```

---

## Environment variables

The API reads these environment variables at process startup:

| Variable                            |   Default | Description                                                  |
|-------------------------------------|----------:|--------------------------------------------------------------|
| `HOST`                              | `0.0.0.0` | Bind address                                                 |
| `PORT`                              |    `9098` | API port                                                     |
| `MAX_CONCURRENT_CRAWLS`             |       `2` | Maximum concurrent chart crawls                              |
| `DEFAULT_TIMEOUT_SECONDS`           |     `120` | Default crawl timeout when a request omits `timeout_seconds` |
| `MAX_TIMEOUT_SECONDS`               |     `600` | Maximum allowed crawl timeout                                |
| `WEBSOCKET_RECEIVE_TIMEOUT_SECONDS` |      `30` | Maximum time to receive the initial WebSocket JSON request   |
| `WEBSOCKET_IDLE_TIMEOUT_SECONDS`    |     `600` | WebSocket crawl/idle execution ceiling                       |

Example `.env/.env.prod`:

```dotenv
HOST=0.0.0.0
PORT=9098
MAX_CONCURRENT_CRAWLS=2
DEFAULT_TIMEOUT_SECONDS=120
MAX_TIMEOUT_SECONDS=600
WEBSOCKET_RECEIVE_TIMEOUT_SECONDS=30
WEBSOCKET_IDLE_TIMEOUT_SECONDS=600
```

### Timeout behavior

`ChartRequest.timeout_seconds` is optional. The Pydantic request model accepts values from `10` through `600` seconds.

If omitted, the service uses `DEFAULT_TIMEOUT_SECONDS`.

The effective timeout can never exceed `MAX_TIMEOUT_SECONDS`.

For the REST endpoint, a crawl timeout becomes:

```http
504 Gateway Timeout
```

For the WebSocket endpoint, the service sends an error message with `status_code: 504` before closing the socket.

---

# API Reference

## 1. `GET /health`

Returns the liveness status of the service.

### Request

```http
GET /health HTTP/1.1
Host: localhost:9098
Accept: application/json
```

### cURL

```bash
curl http://localhost:9098/health
```

### Response

```json
{
  "status": "healthy",
  "service": "dexscreener-charts-crawler",
  "version": "1.0"
}
```

### Semantics

This endpoint does not perform a DexScreener crawl. It only confirms that the FastAPI application is alive and responding.

Use it for a load balancer liveness probe, process supervision, or basic service monitoring.

---

## 2. `GET /ready`

Returns the service readiness state plus the current crawl capacity and timeout configuration.

### Request

```http
GET /ready HTTP/1.1
Host: localhost:9098
Accept: application/json
```

### cURL

```bash
curl http://localhost:9098/ready
```

### Response

```json
{
  "status": "ready",
  "host": "0.0.0.0",
  "port": 9098,
  "available_slots": 2,
  "max_concurrent_crawls": 2,
  "default_timeout_seconds": 120,
  "max_timeout_seconds": 600
}
```

### Response fields

| Field                     | Type    | Meaning                                            |
|---------------------------|---------|----------------------------------------------------|
| `status`                  | string  | Always `ready` when the endpoint responds normally |
| `host`                    | string  | Configured bind host                               |
| `port`                    | integer | Configured API port                                |
| `available_slots`         | integer | Current number of free crawl semaphore slots       |
| `max_concurrent_crawls`   | integer | Configured maximum number of concurrent crawls     |
| `default_timeout_seconds` | integer | Default request timeout                            |
| `max_timeout_seconds`     | integer | Maximum allowed request timeout                    |

`available_slots` is useful for operational monitoring. For example, with `max_concurrent_crawls=2`, a value of `0` means both crawl slots are currently occupied.

---

## 3. `POST /v1/charts`

Crawls a DexScreener pair and returns all candles successfully parsed from the chart payload in one JSON response.

This is the simplest endpoint for batch collection, backtesting, data pipelines, and applications that want the entire result before processing it.

### Request body

```json
{
  "pair": {
    "chain_id": "solana",
    "dex_id": "raydium",
    "pair_address": "<DEXSCREENER_PAIR_ADDRESS>",
    "quote_token_address": "<QUOTE_TOKEN_MINT>",
    "candles_amount": 329,
    "charts_resolution": 5
  },
  "timeout_seconds": 120,
  "proxy": null
}
```

### `pair` fields

| Field                 | Type    |  Default | Constraints | Description                                           |
|-----------------------|---------|---------:|-------------|-------------------------------------------------------|
| `chain_id`            | string  | required | 1-64 chars  | DexScreener chain identifier, normalized to lowercase |
| `dex_id`              | string  | required | 1-64 chars  | DexScreener DEX identifier, normalized to lowercase   |
| `pair_address`        | string  | required | 1-256 chars | Trading pair/pool address                             |
| `quote_token_address` | string  | required | 1-256 chars | Quote asset/token address used by the chart route     |
| `candles_amount`      | integer |    `329` | 1-10,000    | Maximum number of candles requested                   |
| `charts_resolution`   | integer |      `5` | 1-1,440     | Candle interval in minutes                            |

`candles_amount` is a maximum request amount. The service returns the candles that DexScreener provides and that the parser can successfully decode; `count` may therefore be smaller than the requested amount.

### Optional top-level fields

| Field             | Type         | Default | Description                                                      |
|-------------------|--------------|---------|------------------------------------------------------------------|
| `timeout_seconds` | integer/null | `null`  | Request-specific crawl timeout; accepted range is 10-600 seconds |
| `proxy`           | object/null  | `null`  | Optional proxy mapping passed to the crawler's HTTP client       |

Example proxy object:

```json
{
  "proxy": {
    "http": "http://user:password@proxy.example:8080",
    "https": "http://user:password@proxy.example:8080"
  }
}
```

Only string-to-string key/value pairs are accepted for `proxy`.

### cURL example

```bash
curl -X POST "http://localhost:9098/v1/charts" \
  -H "Content-Type: application/json" \
  -d '{
    "pair": {
      "chain_id": "solana",
      "dex_id": "raydium",
      "pair_address": "<DEXSCREENER_PAIR_ADDRESS>",
      "quote_token_address": "<QUOTE_TOKEN_MINT>",
      "candles_amount": 120,
      "charts_resolution": 5
    },
    "timeout_seconds": 120
  }'
```

### Python async example

```python
import httpx2


async def fetch_chart() -> dict:
    payload = {
        "pair": {
            "chain_id": "solana",
            "dex_id": "raydium",
            "pair_address": "<DEXSCREENER_PAIR_ADDRESS>",
            "quote_token_address": "<QUOTE_TOKEN_MINT>",
            "candles_amount": 120,
            "charts_resolution": 5,
        },
        "timeout_seconds": 120,
    }

    async with httpx2.AsyncClient(timeout=130) as client:
        response = await client.post(
            "http://localhost:9098/v1/charts",
            json=payload,
        )
        response.raise_for_status()
        return response.json()
```

### Successful response

The service returns a `ChartResponse` object:

```json
{
  "pair": {
    "chain_id": "solana",
    "dex_id": "raydium",
    "pair_address": "<DEXSCREENER_PAIR_ADDRESS>",
    "quote_token_address": "<QUOTE_TOKEN_MINT>",
    "candles_amount": 120,
    "charts_resolution": 5
  },
  "count": 3,
  "elapsed_ms": 847,
  "charts": [
    {
      "timestamp": 1750000000000,
      "datetime": "2025-06-15T10:13:20+00:00",
      "open": 0.0000012,
      "open_usd": 0.0000012,
      "high": 0.0000014,
      "high_usd": 0.0000014,
      "low": 0.0000011,
      "low_usd": 0.0000011,
      "close": 0.0000013,
      "close_usd": 0.0000013,
      "volume_usd": 18452.73
    }
  ]
}
```

The values above are an illustrative response shape; the actual values depend on the pair and the time of the crawl.

### Response fields

| Field        | Type    | Description                                |
|--------------|---------|--------------------------------------------|
| `pair`       | object  | Normalized request pair                    |
| `count`      | integer | Number of parsed candles returned          |
| `elapsed_ms` | integer | Server-side crawl duration in milliseconds |
| `charts`     | array   | Parsed candle objects                      |

### Candle schema

Each item in `charts` contains:

| Field        | Type    | Description                                       |
|--------------|---------|---------------------------------------------------|
| `timestamp`  | integer | Candle timestamp in milliseconds                  |
| `datetime`   | string  | ISO-8601 UTC timestamp                            |
| `open`       | float   | Opening token price in native/base representation |
| `open_usd`   | float   | Opening price in USD                              |
| `high`       | float   | Highest token price in native/base representation |
| `high_usd`   | float   | Highest price in USD                              |
| `low`        | float   | Lowest token price in native/base representation  |
| `low_usd`    | float   | Lowest price in USD                               |
| `close`      | float   | Closing token price in native/base representation |
| `close_usd`  | float   | Closing price in USD                              |
| `volume_usd` | float   | Candle trading volume in USD                      |

The parser validates the basic OHLC relationships before yielding a candle:

```text
high >= max(open, close)
high_usd >= max(open_usd, close_usd)
low <= min(open, close)
low_usd <= min(open_usd, close_usd)
```

Malformed binary records that fail parsing or OHLC validation are skipped rather than emitted as invalid candle objects.

### HTTP status codes

#### `200 OK`

The crawl completed and a `ChartResponse` was generated. `count` can be `0` when no valid candles were produced.

#### `422 Unprocessable Entity`

Typical causes:

- Invalid Pydantic field value.
- Missing required fields.
- Unsupported `chain_id` + `dex_id` route.
- `timeout_seconds` outside the accepted request-model range.

Example validation response:

```json
{
  "detail": "unsupported chart route: solana/unknown-dex"
}
```

#### `504 Gateway Timeout`

The crawl did not finish before the effective timeout:

```json
{
  "detail": "chart crawl operation timed out"
}
```

#### `500 Internal Server Error`

An unexpected crawler or parsing failure escaped the explicitly handled error cases.

### Extra fields are rejected

The request model uses strict Pydantic configuration with `extra="forbid"`. For example, this is invalid:

```json
{
  "pair": {
    "chain_id": "solana",
    "dex_id": "raydium",
    "pair_address": "<PAIR>",
    "quote_token_address": "<QUOTE>",
    "unexpected": true
  }
}
```

Do not send undocumented fields.

---

## 4. `WS /v1/ws/charts`

Streams parsed candles over a WebSocket connection.

Use this endpoint when the consumer wants to begin processing candles as they arrive instead of waiting for the complete chart crawl.

### Connection

```text
ws://localhost:9098/v1/ws/charts
```

For TLS-enabled deployments:

```text
wss://your-host.example/v1/ws/charts
```

### Protocol

1. Open the WebSocket connection.
2. Send exactly one JSON request containing the same `ChartRequest` structure used by `POST /v1/charts`.
3. Receive zero or more `item` messages.
4. Receive one `done` message when the crawl finishes.
5. The service closes the connection.

### Request example

```json
{
  "pair": {
    "chain_id": "solana",
    "dex_id": "raydium",
    "pair_address": "<DEXSCREENER_PAIR_ADDRESS>",
    "quote_token_address": "<QUOTE_TOKEN_MINT>",
    "candles_amount": 120,
    "charts_resolution": 5
  },
  "timeout_seconds": 120
}
```

### JavaScript example

```javascript
const socket = new WebSocket("ws://localhost:9098/v1/ws/charts");

socket.onopen = () => {
  socket.send(JSON.stringify({
    pair: {
      chain_id: "solana",
      dex_id: "raydium",
      pair_address: "<DEXSCREENER_PAIR_ADDRESS>",
      quote_token_address: "<QUOTE_TOKEN_MINT>",
      candles_amount: 120,
      charts_resolution: 5
    },
    timeout_seconds: 120
  }));
};

socket.onmessage = (event) => {
  const message = JSON.parse(event.data);

  if (message.type === "item") {
    const candle = message.data;
    console.log("candle:", candle.datetime, candle.close_usd);
    return;
  }

  if (message.type === "done") {
    console.log("crawl complete:", message.count);
    socket.close();
    return;
  }

  if (message.type === "error") {
    console.error("crawler error:", message.status_code, message.detail);
  }
};
```

### Python async example

```python
import asyncio
import json
import websockets


async def stream_chart() -> None:
    uri = "ws://localhost:9098/v1/ws/charts"

    request = {
        "pair": {
            "chain_id": "solana",
            "dex_id": "raydium",
            "pair_address": "<DEXSCREENER_PAIR_ADDRESS>",
            "quote_token_address": "<QUOTE_TOKEN_MINT>",
            "candles_amount": 120,
            "charts_resolution": 5,
        },
        "timeout_seconds": 120,
    }

    async with websockets.connect(uri) as websocket:
        await websocket.send(json.dumps(request))

        async for raw_message in websocket:
            message = json.loads(raw_message)

            if message["type"] == "item":
                candle = message["data"]
                print(candle["datetime"], candle["close_usd"])

            elif message["type"] == "done":
                print("completed:", message["count"])
                break

            elif message["type"] == "error":
                raise RuntimeError(
                    f"crawler error {message['status_code']}: {message['detail']}"
                )


asyncio.run(stream_chart())
```

### `item` message

Every parsed candle is wrapped in an `item` envelope:

```json
{
  "type": "item",
  "data": {
    "timestamp": 1750000000000,
    "datetime": "2025-06-15T10:13:20+00:00",
    "open": 0.0000012,
    "open_usd": 0.0000012,
    "high": 0.0000014,
    "high_usd": 0.0000014,
    "low": 0.0000011,
    "low_usd": 0.0000011,
    "close": 0.0000013,
    "close_usd": 0.0000013,
    "volume_usd": 18452.73
  }
}
```

### `done` message

When the crawl finishes normally:

```json
{
  "type": "done",
  "count": 120
}
```

`count` is the number of candles actually streamed. It is not guaranteed to equal the requested `candles_amount`.

### `error` message

WebSocket errors use a normalized envelope:

```json
{
  "type": "error",
  "status_code": 422,
  "detail": "unsupported chart route: solana/unknown-dex"
}
```

Possible status codes emitted by the WebSocket handler include:

| `status_code` | Meaning                                    |
|--------------:|--------------------------------------------|
|         `422` | Invalid request or unsupported route       |
|         `504` | WebSocket receive timeout or crawl timeout |
|         `500` | Unexpected server-side error               |

### WebSocket receive timeout

After the socket is accepted, the service waits up to `WEBSOCKET_RECEIVE_TIMEOUT_SECONDS` for the initial JSON request.

If the client connects but does not send a request in time, the server emits a `504` error message.

### WebSocket execution timeout

The total streaming operation is bounded by the smaller of:

```text
request.timeout_seconds
WEBSOCKET_IDLE_TIMEOUT_SECONDS
```

---

# Supported pair routing

The crawler does not dynamically accept every DexScreener chain/DEX combination. It validates the requested pair against a local route table before building the chart URL.

Current supported combinations:

```text
solana + pumpswap
solana + pumpfun
solana + raydium
solana + meteora
base + uniswap
robinhood + uniswap
```

This is deliberate: the binary DexScreener chart endpoint includes an internal route segment, and the service only knows how to construct routes that are explicitly present in its route table.

When the pair is valid, the crawler constructs the chart request using values derived from the request, including:

- chart resolution (`res`)
- requested candle count (`cb`)
- quote token (`q`)
- chart mode parameters used internally by DexScreener

The service requests an `application/octet-stream` response and parses the returned binary payload.

---

# Concurrency model

The service uses a global asyncio semaphore:

```text
MAX_CONCURRENT_CRAWLS=2
```

with the default configuration.

Every chart crawl must acquire one semaphore slot before the DexScreener request starts. This protects the service from unbounded concurrent outbound crawls.

Example with `MAX_CONCURRENT_CRAWLS=2`:

```text
Request A -> slot 1 -> crawling
Request B -> slot 2 -> crawling
Request C -> waits
Request D -> waits
```

When A or B finishes, the next waiting request may acquire the released slot.

The `/ready` endpoint exposes the current `available_slots` count.

---

# Proxy support

A request can optionally provide a proxy configuration:

```json
{
  "proxy": {
    "http": "http://proxy.example:8080",
    "https": "http://proxy.example:8080"
  }
}
```

The service passes the proxy mapping to the underlying `cloudscraper` HTTP session.

Proxy credentials should not be committed to source control. Prefer environment-level secret management or a protected deployment configuration.

---

# Data semantics

## Timestamp

`timestamp` is an integer Unix timestamp in milliseconds.

`datetime` is derived from the same timestamp and serialized as an ISO-8601 UTC string.

Example:

```text
timestamp: 1750000000000
datetime: 2025-06-15T10:13:20+00:00
```

## Native price vs USD price

Each OHLC value is represented twice:

```text
open / high / low / close
```

and:

```text
open_usd / high_usd / low_usd / close_usd
```

This gives consumers both the parsed chart value and its USD representation without requiring another transformation layer.

## Volume

`volume_usd` is the candle's USD trading volume as reported in the chart payload.

---

# Error handling and validation

The service performs validation at several layers:

### Request-model validation

Pydantic validates:

- required fields
- string lengths
- integer bounds
- optional field types
- forbidden extra fields

### Route validation

The pair validator verifies that `(chain_id, dex_id)` exists in the supported route table.

### Runtime timeout enforcement

A monotonic deadline is created for each crawl. The remaining time is applied to each async generator step, so a slow crawl cannot continue indefinitely.

### Binary payload validation

The chart parser checks the binary payload for expected candle markers, decodes all required numeric values, and validates OHLC relationships before yielding a candle.

---

# Testing

Run the test suite with:

```bash
uv run pytest
```

The project configures pytest with:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["src"]
```

The repository's tests cover route/parser behavior under the current project structure. Keep API tests close to the same conventions when adding endpoint-level coverage.

For a real integration test against DexScreener, use a known-good pair and run it separately from deterministic parser/unit tests so external availability does not make the unit suite flaky.

---

# Docker

The repository includes a Dockerfile and Docker Compose configuration.

Build the image:

```bash
docker build -t dexscreener-crawler:latest .
```

Run the container:

```bash
docker run --rm \
  -p 9098:9098 \
  -e HOST=0.0.0.0 \
  -e PORT=9098 \
  dexscreener-crawler:latest
```

The image exposes port `9098` and starts Uvicorn through `tini`.

## Docker Compose

The included `docker-compose.yml` reads production configuration from:

```text
./.env/.env.prod
```

and publishes the configured `${PORT}`.

Start it with:

```bash
docker compose up -d --build
```

Inspect logs:

```bash
docker compose logs -f app
```

Check the service:

```bash
curl http://localhost:9098/health
curl http://localhost:9098/ready
```

The Compose configuration also attaches the service to an external Docker network named `crawlers-network` and mounts a `dexscreener_logs` volume at `/app/logs`.

Make sure the external network exists before starting Compose:

```bash
docker network create crawlers-network
```

If it already exists, the command returns an error; that is harmless.

---

# Operational recommendations

## Use `/health` for liveness

A process that responds to `/health` is alive. It does not mean DexScreener is reachable.

## Use `/ready` for readiness

Use `/ready` to inspect the current crawl capacity and configured timeout limits before routing workload to the service.

## Prefer `POST /v1/charts` for batch pipelines

Use the REST endpoint when the downstream job needs the complete result as one object, for example:

- historical backtesting
- ETL ingestion
- storing candle arrays in a database/object store
- one-shot analysis

## Prefer WebSocket for incremental consumers

Use `WS /v1/ws/charts` when downstream processing can start before the entire chart has been received.

## Keep timeouts realistic

Increasing the timeout does not create more DexScreener data. It only gives a slow crawl more time to finish.

## Avoid uncontrolled parallelism

The service intentionally limits concurrent crawls. Increasing `MAX_CONCURRENT_CRAWLS` should be done together with monitoring of outbound traffic, latency, error rates, and the behavior of the upstream chart endpoint.

---

# Example integration flow for a backtesting system

A typical consumer can use the service like this:

```text
1. Identify a DEX pair.
2. Determine the chain_id + dex_id.
3. Determine the quote token address.
4. Request candles at the required resolution.
5. Receive normalized OHLCV candles.
6. Convert `datetime` to the backtest timezone if needed.
7. Build indicators/signals from the candle series.
8. Persist the raw candle response if reproducibility is important.
```

For example, a 5-minute request for 329 candles covers approximately:

```text
329 × 5 minutes = 1,645 minutes
≈ 27.4 hours
```

This is approximate chart coverage; the actual returned history depends on the upstream data available for the pair.

---

# API documentation

Because this service is built with FastAPI, interactive documentation is generated automatically.

When running locally:

- Swagger UI: `http://localhost:9098/docs`
- ReDoc: `http://localhost:9098/redoc`

These are the fastest way to inspect the generated OpenAPI schema while developing a client.

---

# Project structure

The core source tree is organized around the API, crawler, models, and utilities:

```text
src/
├── api.py
├── main.py
├── __main__.py
├── crawler/
│   ├── dexscreener.py
│   └── chart_parser.py
├── items/
│   ├── candle.py
│   ├── pair.py
│   └── schemas.py
└── util/
    └── utils.py
```

Important responsibilities:

- `src/api.py` — FastAPI application, endpoint handlers, timeout handling, concurrency gate, and WebSocket protocol.
- `src/crawler/dexscreener.py` — DexScreener URL generation, HTTP request, and async candle generation.
- `src/crawler/chart_parser.py` — binary response decoding and OHLC validation.
- `src/items/pair.py` — request pair validation and supported route checking.
- `src/items/candle.py` — normalized candle model.
- `src/items/schemas.py` — `ChartRequest` and `ChartResponse` schemas.
- `src/util/utils.py` — supported chain/DEX route map.

---

# Important limitations

### This is not the public DexScreener JSON API

The crawler requests DexScreener's binary chart endpoint and parses the binary response. It therefore depends on the current response format and internal route structure used by the chart service.

### Route support is explicit

A newly added DexScreener chain or DEX is not automatically supported. It must be added to the service's route mapping with the correct internal chart route.

### Upstream availability affects results

A successful request to this microservice depends on the upstream DexScreener chart endpoint being reachable and returning a payload that the parser recognizes.

### A successful HTTP response does not guarantee a full candle set

The `count` field is the number of candles actually parsed and returned. It can be smaller than `candles_amount`.

---

# License

This project is licensed under the MIT License.

See [`LICENSE`](./LICENSE) for the full license text.

---

# Repository

#### [GitHub](https://github.com/G-Glitch404/DexScreenerChartsCrawler)
