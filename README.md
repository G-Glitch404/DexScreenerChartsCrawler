# Memecoins Charts Crawler

A FastAPI microservice for retrieving normalized OHLCV market data for memecoins from multiple chart-data providers.

The service provides a stable HTTP interface in front of provider-specific chart implementations, currently supporting **DexScreener** and **Birdeye** crawlers. Provider responses are converted into typed Pydantic candle models so downstream systems can consume chart data without depending on provider-specific response formats.

The project is designed as an independent microservice for trading systems, risk engines, pattern-recognition systems, backtesting pipelines, market scanners, data collectors, and other services that need normalized historical candle data.

## Overview

The crawler sits between an application that needs chart data and the external market-data provider that supplies it.

```text
Consumer
   |
   | HTTP POST /v1/charts
   v
FastAPI
   |
   | validate request
   | select crawler
   | enforce concurrency
   | enforce timeout
   v
+--------------------------+
| Provider Crawler         |
|                          |
|  DexScreener             |
|  or                      |
|  Birdeye                 |
+--------------------------+
   |
   v
Provider API / chart source
   |
   | provider-specific response
   v
Normalizer
   |
   v
Typed candle objects
   |
   v
JSON response
```

The important architectural boundary is the crawler interface.

Consumers do not need to know how DexScreener's chart payload is encoded or how Birdeye represents OHLCV records. They submit a normalized `Pair` request and select the desired provider.

## Why this service exists

Market-data consumers often become tightly coupled to the source that provides their candles.

Without a dedicated service, a downstream application typically ends up containing:

* provider-specific HTTP clients
* provider-specific authentication
* provider-specific request construction
* provider-specific response parsing
* provider-specific timestamp handling
* provider-specific OHLC normalization
* provider-specific error handling
* provider-specific retry and timeout behavior

That becomes especially problematic when a provider becomes unreliable for a particular chain, DEX, pair, or endpoint.

This project isolates those concerns inside crawler implementations.

The consumer sees a consistent interface:

```text
Pair
  ↓
Crawler
  ↓
AsyncGenerator[Candle]
```

while the provider-specific implementation can evolve independently.

## Current providers

### DexScreener

The DexScreener crawler retrieves chart data through DexScreener's chart infrastructure and parses the provider's binary chart payload into normalized `DexscreenerCandle` objects.

The implementation contains provider-specific routing logic because the chart endpoint is not simply a generic `chain + dex + pair` endpoint. The repository maintains an explicit route table for supported combinations.

The currently configured route table includes:

| Chain       | DEX        | Internal route |
|-------------|------------|----------------|
| `solana`    | `pumpswap` | `pumpfundex`   |
| `solana`    | `pumpfun`  | `pumpfundex`   |
| `solana`    | `raydium`  | `solamm`       |
| `solana`    | `meteora`  | `meteora`      |
| `base`      | `uniswap`  | `uniswapv4`    |
| `robinhood` | `uniswap`  | `uniswapv4`    |

Unsupported combinations are rejected before the provider request is constructed.

### Birdeye

The Birdeye crawler was added to provide an alternative source of OHLCV chart data and to reduce dependence on DexScreener's binary chart infrastructure.

The current implementation uses Birdeye's pair OHLCV endpoint, sends the API key through `X-API-KEY`, supplies the chain through `x-chain`, converts supported resolutions into Birdeye interval names, validates numeric values, and normalizes records into `BirdeyeCandle` objects.

Supported minute resolutions currently map to Birdeye intervals as follows:

| Resolution | Birdeye interval |
|-----------:|------------------|
|          1 | `1m`             |
|          3 | `3m`             |
|          5 | `5m`             |
|         15 | `15m`            |
|         30 | `30m`            |
|         60 | `1H`             |
|        120 | `2H`             |
|        240 | `4H`             |
|        360 | `6H`             |
|        480 | `8H`             |
|        720 | `12H`            |
|       1440 | `1D`             |
|       4320 | `3D`             |
|      10080 | `1W`             |
|      43200 | `1M`             |

The crawler caps the requested candle count at 5000 before making the provider request.

The Birdeye crawler currently expects a valid Birdeye-compatible pair address. A DexScreener pair address being syntactically valid does not by itself guarantee that Birdeye indexes the same pool.

## Candle models

Provider-specific response differences are represented explicitly.

### `DexscreenerCandle`

The DexScreener candle contains:

| Field        | Type    | Description                                       |
|--------------|---------|---------------------------------------------------|
| `timestamp`  | `int`   | Candle timestamp in milliseconds                  |
| `datetime`   | `str`   | ISO-8601 UTC timestamp                            |
| `ohlc_valid` | `bool`  | Whether the OHLC relationship is internally valid |
| `direction`  | `str`   | `bullish`, `bearish`, or `doji`                   |
| `open`       | `float` | Opening token price                               |
| `open_usd`   | `float` | Opening price in USD                              |
| `high`       | `float` | High token price                                  |
| `high_usd`   | `float` | High price in USD                                 |
| `low`        | `float` | Low token price                                   |
| `low_usd`    | `float` | Low price in USD                                  |
| `close`      | `float` | Closing token price                               |
| `close_usd`  | `float` | Closing price in USD                              |
| `volume_usd` | `float` | USD trading volume                                |

### `BirdeyeCandle`

Birdeye uses a separate model because its pair OHLCV endpoint does not provide the exact same normalized structure as the DexScreener implementation.

| Field        | Type    | Description                                       |
|--------------|---------|---------------------------------------------------|
| `timestamp`  | `int`   | Candle timestamp in milliseconds                  |
| `datetime`   | `str`   | ISO-8601 UTC timestamp                            |
| `ohlc_valid` | `bool`  | Whether the OHLC relationship is internally valid |
| `direction`  | `str`   | `bullish`, `bearish`, or `doji`                   |
| `open`       | `float` | Opening price                                     |
| `high`       | `float` | High price                                        |
| `low`        | `float` | Low price                                         |
| `close`      | `float` | Closing price                                     |
| `volume_usd` | `float` | USD trading volume                                |

Both models deliberately use `extra="forbid"` so unexpected fields do not silently enter the normalized data model.

## Candle semantics

The crawler does more than deserialize provider values.

Each normalized candle contains explicit semantic fields that allow downstream systems to make decisions without repeatedly reimplementing basic candle validation.

### OHLC validity

A candle is considered OHLC-valid when:

```text
high >= max(open, close)
low  <= min(open, close)
```

The DexScreener implementation also checks the USD representation:

```text
high_usd >= max(open_usd, close_usd)
low_usd  <= min(open_usd, close_usd)
```

Malformed numeric values and negative volumes are rejected during parsing, while the semantic validity itself is preserved in `ohlc_valid` rather than silently discarding every structurally unusual candle. This change was introduced specifically to replace the older approach that dropped semantically invalid candles during parsing.

### Candle direction

The normalized `direction` field is derived from the opening and closing prices:

```text
close > open  → bullish
close < open  → bearish
close == open → doji
```

This is useful for pattern recognition and downstream analytical systems because they no longer need to derive the basic candle direction independently.

## Request model

The public API uses a Pydantic `ChartRequest` model.

A request contains:

```json
{
  "pair": {
    "chain_id": "solana",
    "dex_id": "raydium",
    "pair_address": "PAIR_ADDRESS",
    "quote_token_address": "QUOTE_TOKEN_ADDRESS",
    "candles_amount": 120,
    "charts_resolution": 5
  },
  "crawler": "dexscreener",
  "timeout_seconds": 120,
  "proxy": null
}
```

The supported crawler values are:

```text
dexscreener
birdeye
```

The API request schema rejects unexpected fields through Pydantic's `extra="forbid"` configuration.

## Pair model

`Pair` is the central input model shared by both crawler implementations.

It contains the market information necessary for chart retrieval:

```text
chain_id
dex_id
pair_address
quote_token_address
candles_amount
charts_resolution
```

The model also validates the requested pair against the locally supported routing rules where the provider requires explicit route construction.

A typical pair looks like:

```json
{
  "chain_id": "solana",
  "dex_id": "raydium",
  "pair_address": "PAIR_ADDRESS",
  "quote_token_address": "QUOTE_TOKEN_MINT",
  "candles_amount": 120,
  "charts_resolution": 5
}
```

## API

The service exposes a small FastAPI interface.

| Method | Endpoint        | Purpose                             |
|--------|-----------------|-------------------------------------|
| `GET`  | `/health`       | Process liveness                    |
| `GET`  | `/ready`        | Runtime readiness and capacity      |
| `POST` | `/v1/charts`    | Retrieve complete candle history    |
| `WS`   | `/v1/ws/charts` | Stream candle history incrementally |

The current repository still exposes both REST and WebSocket chart interfaces.

### `GET /health`

Returns the basic process health state.

Example:

```bash
curl http://localhost:9098/health
```

Example response:

```json
{
  "status": "healthy",
  "service": "dexscreener-charts-crawler",
  "version": "1.0"
}
```

This endpoint does not perform a provider request and should be used as a liveness check rather than a dependency-availability check.

### `GET /ready`

Returns service capacity and timeout configuration.

Example:

```bash
curl http://localhost:9098/ready
```

Example response:

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

`available_slots` represents the currently unused crawler semaphore capacity.

### `POST /v1/charts`

This is the primary REST interface.

Example:

```bash
curl -X POST "http://localhost:9098/v1/charts" \
  -H "Content-Type: application/json" \
  -d '{
    "pair": {
      "chain_id": "solana",
      "dex_id": "raydium",
      "pair_address": "PAIR_ADDRESS",
      "quote_token_address": "QUOTE_TOKEN_MINT",
      "candles_amount": 120,
      "charts_resolution": 5
    },
    "crawler": "dexscreener",
    "timeout_seconds": 120
  }'
```

Successful responses contain:

```json
{
  "pair": {
    "chain_id": "solana",
    "dex_id": "raydium",
    "pair_address": "PAIR_ADDRESS",
    "quote_token_address": "QUOTE_TOKEN_MINT",
    "candles_amount": 120,
    "charts_resolution": 5
  },
  "crawler": "dexscreener",
  "count": 120,
  "elapsed_ms": 847,
  "charts": []
}
```

`count` is the number of successfully parsed candles, not necessarily the number requested.

## Choosing a crawler

A request explicitly selects its provider:

```json
{
  "crawler": "dexscreener"
}
```

or:

```json
{
  "crawler": "birdeye"
}
```

This separation is intentional.

DexScreener and Birdeye do not expose identical response formats, pair indexing, routing rules, or data semantics. The API allows the caller to choose the provider instead of hiding provider selection inside an opaque fallback system.

This is particularly useful for a larger market-data pipeline where one upstream provider can be used as the primary source and another can be used for alternative coverage or comparison.

## Timeout handling

The service supports a request-specific timeout.

The timeout is applied to the complete crawl operation rather than only to the initial HTTP connection.

The service creates a monotonic deadline and applies the remaining time to asynchronous crawler iteration. This prevents a generator that keeps producing slowly from running indefinitely.

The request model currently accepts timeout values between 10 and 600 seconds.

Example:

```json
{
  "timeout_seconds": 120
}
```

If the crawl exceeds its effective timeout, the REST endpoint returns:

```text
504 Gateway Timeout
```

## Concurrency control

The API uses a global `asyncio.Semaphore` to prevent unbounded simultaneous chart crawls.

The default configuration is:

```text
MAX_CONCURRENT_CRAWLS=2
```

With two available crawler slots:

```text
Request A → crawling
Request B → crawling
Request C → waiting
Request D → waiting
```

When A or B finishes, another queued request can acquire the released slot.

This protects both the microservice and upstream providers from uncontrolled parallelism.

Concurrency should be increased carefully because it affects outbound request pressure, latency, provider throttling, and service resource consumption.

## Provider rate limits

Provider rate limits are upstream concerns and should not be confused with this service's concurrency setting.

For example:

```text
MAX_CONCURRENT_CRAWLS=10
```

does not mean the upstream provider permits 10 requests per second.

The crawler implementation must respect the limits of the provider it is using.

The current Birdeye implementation performs one OHLCV request per crawl and currently does not document a built-in global one-request-per-second scheduler. Deployments using a plan with strict request-per-second limits should account for this at the crawler/client layer before increasing concurrency.

This distinction is important:

```text
Concurrency limit
    =
How many crawls may run at once

Rate limit
    =
How frequently provider requests may be sent
```

They solve different problems.

## Proxy support

The request model supports an optional proxy mapping.

Example:

```json
{
  "proxy": {
    "http": "http://proxy.example:8080",
    "https": "http://proxy.example:8080"
  }
}
```

Proxy configuration is passed to the underlying crawler implementation.

Proxy credentials should never be committed to the repository.

## Error handling

The API normalizes common crawler failures into HTTP status codes.

| Status | Meaning                              |
|-------:|--------------------------------------|
|  `200` | Successful crawl                     |
|  `422` | Invalid request or unsupported route |
|  `504` | Crawl timeout                        |
|  `500` | Unexpected crawler or server failure |

Examples of `422` causes include:

* missing required fields
* invalid field values
* unsupported crawler identifier
* unsupported DexScreener route
* invalid timeout configuration

An upstream provider error is surfaced as a crawler exception and converted into a server error unless explicitly handled as a validation or timeout failure.

## REST response structure

The response contains:

```text
pair
crawler
count
elapsed_ms
charts
```

### `pair`

The normalized `Pair` used for the crawl.

### `crawler`

The provider selected for the operation.

### `count`

The number of candles successfully normalized.

### `elapsed_ms`

Server-side crawl duration.

### `charts`

The normalized candle collection.

## Example response

```json
{
  "pair": {
    "chain_id": "solana",
    "dex_id": "raydium",
    "pair_address": "PAIR_ADDRESS",
    "quote_token_address": "QUOTE_TOKEN_MINT",
    "candles_amount": 5,
    "charts_resolution": 5
  },
  "crawler": "birdeye",
  "count": 5,
  "elapsed_ms": 921,
  "charts": [
    {
      "timestamp": 1750000000000,
      "datetime": "2025-06-15T10:13:20+00:00",
      "ohlc_valid": true,
      "direction": "bullish",
      "open": 0.0000012,
      "high": 0.0000014,
      "low": 0.0000011,
      "close": 0.0000013,
      "volume_usd": 18452.73
    }
  ]
}
```

The exact candle fields depend on the selected crawler implementation.

## Architecture

The source tree is organized around provider implementations, domain models, parsing utilities, and the API layer.

```text
MemecoinsChartsCrawler/
├── .env/
│   ├── .env.example
│   └── .env.prod
├── src/
│   ├── crawler/
│   │   ├── __init__.py
│   │   ├── _dexscreener_charts_parser.py
│   │   ├── birdeye.py
│   │   └── dexscreener.py
│   ├── items/
│   │   ├── __init__.py
│   │   ├── candle.py
│   │   ├── pair.py
│   │   └── schemas.py
│   ├── util/
│   │   └── utils.py
│   ├── __init__.py
│   ├── __main__.py
│   ├── api.py
│   └── main.py
├── tests/
│   └── test_service.py
├── .dockerignore
├── .gitignore
├── CHANGELOG.md
├── Dockerfile
├── LICENSE
├── README.md
├── docker-compose.yml
├── pyproject.toml
└── uv.lock
```

The repository intentionally keeps provider-specific implementations separate while sharing the domain models where appropriate.

## Running locally

### Requirements

The project currently targets:

```text
Python >= 3.12
Python < 3.13
uv
```

The dependency set includes FastAPI, Uvicorn, Pydantic, Pydantic Settings, HTTPX2, and Cloudsraper for the DexScreener crawler. Development dependencies include pytest and pytest-asyncio.

### Clone

```bash
git clone REPOSITORY
cd MemecoinsChartsCrawler
```

### Install

```bash
uv sync --locked
```

### Configure environment

Create the production-style environment file from the example:

```text
.env/.env.example
```

The Birdeye crawler expects:

```env
BIRDEYE_API_KEY=your-api-key
```

The service-level configuration contains values such as:

```env
HOST=0.0.0.0
PORT=9098
MAX_CONCURRENT_CRAWLS=2
DEFAULT_TIMEOUT_SECONDS=120
MAX_TIMEOUT_SECONDS=600
```

Never commit a populated secrets file.

### Start the API

```bash
uv run uvicorn src.api:app --host 0.0.0.0 --port 9098
```

The service is then available at:

```text
http://127.0.0.1:9098
```

FastAPI documentation is available at:

```text
http://127.0.0.1:9098/docs
http://127.0.0.1:9098/redoc
```

## Running with Docker

The project includes a Dockerfile based on:

```text
python:3.12-slim-bookworm
```

The current image installs only the minimal operating-system packages required by the service, including `ca-certificates`, `curl`, and `tini`.

Chromium and Chromium Driver are no longer installed because the project no longer requires Selenium/Chrome for chart retrieval. The September 9, 2026 Docker change removed the browser binaries, browser environment variables, and browser-specific system libraries from the image.

### Build

```bash
docker build -t memecoins-charts-crawler:latest .
```

### Run

```bash
docker run --rm \
  -p 9098:9098 \
  --env-file .env/.env.prod \
  memecoins-charts-crawler:latest
```

The container launches Uvicorn through `tini`.

## Docker Compose

The repository includes a single-service Compose deployment.

The service uses:

```text
.env/.env.prod
```

and is attached to the external Docker network:

```text
crawlers-network
```

The network must already exist.

Create it once:

```bash
docker network create crawlers-network
```

Then start the service:

```bash
docker compose up -d --build
```

Inspect logs:

```bash
docker compose logs -f app
```

Check health:

```bash
curl http://localhost:9098/health
```

Check readiness:

```bash
curl http://localhost:9098/ready
```

The current Compose setup also supports configurable ports and environment variables through `.env/.env.prod`.

## Testing

Run the test suite with:

```bash
uv run pytest
```

The project configures pytest for automatic asynchronous test handling:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["src"]
```

The service test suite covers request validation, crawler interaction, parser behavior, REST handling, and WebSocket behavior in the current repository.

## Testing philosophy

The crawler is an external-data integration service, so tests fall into two broad categories.

### Deterministic tests

These should test:

* request validation
* Pair validation
* route selection
* parser behavior
* candle normalization
* malformed record handling
* timeout behavior
* API error handling
* crawler selection
* response schema

These tests should not depend on live provider availability.

### Integration tests

These test:

* actual provider connectivity
* authentication
* provider-side pair availability
* real chart responses
* live candle normalization

Integration tests should be treated separately from deterministic unit/API tests because provider availability, data coverage, throttling, and external behavior can change independently of the code.

## Data quality

The crawler intentionally distinguishes between:

```text
Parsing validity
and
Market-data semantic validity
```

A record can be successfully decoded while still having an OHLC relationship that deserves inspection.

That is why the normalized candle contains:

```text
ohlc_valid
```

instead of automatically discarding every semantically unusual candle.

This is particularly important for memecoin analysis because extreme candles are not necessarily noise. A large candle may represent exactly the event a downstream risk engine is trying to identify.

For example:

```text
steady bullish staircase
        ↓
large pump
        ↓
single catastrophic red candle
```

An aggressive parser that removes the abnormal candle may destroy the evidence required for downstream pattern recognition.

## Usage in a pattern-recognition system

A typical consumer can request candles and feed them directly into an analytical pipeline.

```text
Memecoin discovery
        ↓
Pair resolution
        ↓
Memecoins Charts Crawler
        ↓
Normalized candles
        ↓
Pattern Recognition
        ↓
Risk Assessment
        ↓
Trade / Watch / Reject
```

The normalized candle structure is intended to make the chart service interchangeable with the downstream analytics layer.

The pattern-recognition system can work from:

```text
timestamp
datetime
ohlc_valid
direction
open
high
low
close
volume_usd
```

without knowing whether the original record came from DexScreener or Birdeye.

## Using the crawler as a library

The provider crawlers can also be used directly without the FastAPI layer.

Example:

```python
import asyncio

from src.crawler.birdeye import BirdeyeCrawler
from src.items.pair import Pair


async def main():
    pair = Pair(
        chain_id="solana",
        dex_id="raydium",
        pair_address="PAIR_ADDRESS",
        quote_token_address="QUOTE_TOKEN_ADDRESS",
        candles_amount=100,
        charts_resolution=5,
    )

    crawler = BirdeyeCrawler()

    try:
        async for candle in crawler.crawl_charts(pair):
            print(candle)
    finally:
        await crawler.close()


asyncio.run(main())
```

The same general interface is used by the DexScreener crawler:

```python
async for candle in crawler.crawl_charts(pair):
    ...
```

This is one of the core design goals of the project.

## Provider independence

The project does not attempt to pretend that all providers are identical.

Instead, it separates:

```text
Shared request model
        +
Provider-specific candle model
        +
Provider-specific crawler
```

This is preferable to forcing incompatible provider responses into an artificial universal schema.

For example:

```text
DexScreener
    → DexscreenerCandle
    → native price + USD OHLC + USD volume

Birdeye
    → BirdeyeCandle
    → normalized OHLC + USD volume
```

The API response identifies the selected crawler so consumers know which provider produced the returned dataset.

## Operational recommendations

### Use `/health` for liveness

A successful `/health` request confirms that the application process is responding.

It does not prove that DexScreener or Birdeye is reachable.

### Use `/ready` for capacity visibility

`/ready` exposes the current crawler semaphore capacity and service timeout configuration.

This can be useful for container orchestration and operational diagnostics.

### Keep provider concurrency controlled

Increasing:

```env
MAX_CONCURRENT_CRAWLS
```

can increase upstream pressure even when your application itself has enough CPU and memory.

Provider request-per-second limits should be evaluated separately.

### Preserve raw data for difficult cases

For backtesting and chart-pattern research, preserving the original normalized candle sequence is valuable.

This makes it possible to:

* reproduce a detected pattern
* compare provider outputs
* debug parsing anomalies
* improve pattern-recognition algorithms
* build labeled training datasets
* investigate false positives and false negatives

## Known limitations

### DexScreener routing is explicit

The DexScreener crawler currently depends on a local route table instead of dynamically accepting every chain/DEX combination. New chain or DEX combinations therefore require route support to be added.

### Birdeye pair coverage is provider-dependent

A pair visible in DexScreener is not automatically guaranteed to be queryable through Birdeye's pair OHLCV endpoint.

Applications that use both providers should treat provider availability as independent.

### Provider schemas are not identical

`DexscreenerCandle` and `BirdeyeCandle` intentionally expose slightly different normalized fields.

Consumers that need a fully provider-neutral schema may add their own application-level normalization layer.

### Rate limits remain provider constraints

The service's concurrency semaphore should not be interpreted as an upstream quota manager.

Provider-specific request limits must be respected independently.

### No guarantee of complete historical coverage

A request for N candles represents a maximum requested amount.

The provider may return fewer candles due to:

* pair age
* provider indexing
* missing historical data
* provider-side limitations
* malformed or rejected records

Therefore:

```text
requested candles != guaranteed returned candles
```

## Security considerations

### API keys

Birdeye API keys must be supplied through environment configuration.

Do not:

* commit secrets
* hardcode API keys
* print API keys
* include provider credentials in test fixtures
* include populated production `.env` files in source control

### Proxies

Proxy credentials should be treated as secrets.

Do not embed production proxy credentials in request examples or repository files.

### External input

All public request models use strict Pydantic validation.

Unexpected fields are rejected rather than silently accepted.

## Development

The project uses `uv` for dependency resolution and lockfile-based reproducibility.

Install the locked environment:

```bash
uv sync --locked
```

Run tests:

```bash
uv run pytest
```

Run the API:

```bash
uv run uvicorn src.api:app --host 0.0.0.0 --port 9098
```

The repository also contains Ruff configuration with a 100-character line length and basic error/import linting.

## Dependency management

The current project declares:

```text
httpx2
cloudscraper
fastapi
pydantic
pydantic-settings
uvicorn[standard]
```

Development dependencies include:

```text
pytest
pytest-asyncio
```

Python is constrained to:

```text
>=3.12,<3.13
```

The project keeps `uv.lock` committed so deployments can reproduce the locked environment.

## Project status

The repository is an actively evolving internal microservice rather than a frozen release.

Recent work has focused on:

* provider abstraction
* Birdeye integration
* normalized provider-specific candle models
* semantic candle metadata
* parser refactoring
* test refactoring
* Docker simplification
* removal of browser dependencies
* production-oriented container deployment

The current repository contains 32 commits on `master`.

## Roadmap

The architecture leaves room for several extensions.

### Additional data providers

The provider boundary makes it possible to add additional chart sources without changing the external API contract significantly.

### Provider fallback

A future version could support controlled fallback behavior such as:

```text
Primary provider
      ↓
provider unavailable?
      ↓
Secondary provider
      ↓
normalized candles
```

Such a feature should be explicit because provider datasets are not guaranteed to be equivalent.

### Stronger provider-aware rate limiting

Provider-specific rate limiters can be added at the crawler layer so that application-level concurrency and upstream request-per-second limits remain separate.

### Better data provenance

Future versions could attach provider metadata such as:

```text
provider
provider_pair
provider_timestamp
request_time
```

to improve downstream reproducibility.

### Unified candle protocol

A future shared protocol could formalize the minimum candle interface across providers without forcing all providers to expose identical additional fields.

## License

This project is released under the MIT License.

See `LICENSE` for the complete license text.

## Contributing

Contributions should preserve the separation between:

```text
API
 ↓
request model
 ↓
crawler
 ↓
provider parser
 ↓
normalized domain object
```

When adding a provider:

1. Add a provider-specific crawler implementation
2. Add a provider-specific candle model when the provider schema differs
3. Add provider-specific normalization and validation
4. Update the API crawler selector
5. Add deterministic tests
6. Add integration tests where practical
7. Update the README
8. Update the changelog

Avoid moving provider-specific behavior into the API layer.

## Changelog

See `CHANGELOG.md` for the project history.

## Repository

The project is maintained in the `MemecoinsChartsCrawler` repository under the `G-Glitch404` GitHub organization.
