# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses Semantic Versioning for future stable releases.

## [Unreleased]

The project is currently under active development and does not yet have a stable tagged release.

### Planned

* Provider-aware rate limiting
* Additional chart-data providers
* More deterministic tests for provider-specific normalization
* Improved provider fallback strategies
* Expanded integration-test coverage
* More complete provider coverage across chains and DEXes

---

## [2026-09-09]

### Removed

* Removed Chromium from the Docker image
* Removed Chromium Driver from the Docker image
* Removed `CHROME_BIN` from the container environment
* Removed `CHROMEDRIVER` from the container environment
* Removed browser-specific system libraries from the Docker image
* Removed unnecessary desktop/browser runtime dependencies

### Changed

* Simplified the Docker image to use only the operating-system packages required by the current HTTP-based crawler architecture
* Reduced the container dependency footprint
* Removed Selenium/browser infrastructure requirements from the deployment image
* Kept `tini` as the container init process for proper signal handling

The Docker image now uses the `python:3.12-slim-bookworm` base image with a minimal dependency layer. The browser removal eliminated the previous Chromium and ChromeDriver installation entirely. This change was implemented in commit `6dfd267`.

---

## [2026-09-07]

### Added

* Added Birdeye as an alternative chart-data provider
* Added a dedicated `BirdeyeCrawler`
* Added provider-specific `BirdeyeCandle` normalization
* Added crawler selection to the public chart request schema
* Added Birdeye API-key configuration through `BIRDEYE_API_KEY`

### Changed

* Refactored the crawler API to support:

```text
dexscreener
birdeye
```

* Changed the candle model from a single provider-neutral `Candle` implementation into provider-specific models
* Updated chart request and response models to identify the selected crawler
* Updated the service API to instantiate the requested crawler implementation
* Added Birdeye interval conversion from minute-based chart resolutions
* Added Birdeye OHLCV validation and candle-direction normalization
* Added a maximum of 5000 candles for Birdeye requests

The initial Birdeye API integration changed four files and added 174 lines while replacing 44 lines.

### Birdeye candle normalization

Birdeye records are now normalized into:

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

The implementation reads Birdeye OHLCV values, validates numeric values and volume, converts Unix timestamps to milliseconds, derives UTC ISO-8601 timestamps, and calculates candle direction.

---

## [2026-09-07]

### Changed

* Refactored crawler implementations to share the same `crawl_charts(pair)` public interface
* Established separate provider implementations under `src/crawler`
* Kept provider-specific request and response handling inside each crawler
* Added the structure necessary for using an alternative provider when DexScreener chart retrieval is unsuitable

This refactoring established the current multi-provider architecture.

---

## [2026-09-07]

### Changed

* Renamed project files as part of the crawler refactor
* Updated imports and package references to match the reorganized provider structure

---

## [2026-09-07]

### Changed

* Updated project dependencies for the provider and API refactoring
* Updated the lockfile to preserve reproducible environments
* Continued standardization on Python `>=3.12,<3.13`

The current project configuration uses FastAPI, Uvicorn, Pydantic, Pydantic Settings, HTTPX2, and Cloudsraper, with pytest and pytest-asyncio for development.

---

## [2026-09-06]

### Changed

* Removed the previous parser behavior that discarded candles solely because their OHLC relationships were semantically inconsistent
* Added explicit `ohlc_valid` candle metadata
* Added explicit `direction` metadata
* Preserved structurally unusual candles so downstream systems can decide how to treat them
* Added finite-number validation to parser output
* Added negative-volume rejection

The parser now distinguishes between successfully decoded numerical data and the semantic validity of OHLC relationships.

### Why this changed

The previous parser behavior was:

```text
decode candle
    ↓
semantic validation fails
    ↓
discard candle
```

The new behavior is:

```text
decode candle
    ↓
numerical validation
    ↓
calculate ohlc_valid
    ↓
calculate direction
    ↓
return candle
```

This preserves extreme market events instead of treating them automatically as parser noise.

For a memecoin chart-analysis system, that distinction is important because abnormal candles can represent exactly the collapse, pump, or manipulation event a downstream model is attempting to detect.

---

## [2026-09-06]

### Changed

* Removed unused imports introduced during previous refactoring
* Cleaned the test and crawler modules after the parser changes

---

## [2026-09-05]

### Added

* Added updated project README documentation
* Added project changelog
* Documented API behavior
* Documented Docker deployment
* Documented request/response models
* Documented chart routing
* Documented timeout and concurrency behavior
* Documented testing conventions

### Note

The original documentation became stale shortly after the provider architecture changed. The current README supersedes the earlier DexScreener-only documentation and reflects the multi-provider implementation.

---

## [2026-09-05]

### Removed

* Removed unnecessary tests after the crawler architecture was refactored
* Reduced tests that no longer represented the current provider boundary

### Changed

* Refactored service tests around the current crawler interface
* Continued separating deterministic API behavior from provider-specific crawling behavior

---

## [2026-09-05]

### Changed

* Updated dependency definitions after the crawler refactor
* Refreshed the lockfile
* Kept production and development dependencies separated

---

## [2026-09-05]

### Changed

* Refactored the DexScreener crawler
* Simplified provider-specific request handling
* Kept chart retrieval behind the `crawl_charts(pair)` asynchronous generator interface
* Preserved the binary response parser as a dedicated component

---

## [2026-09-05]

### Removed

* Removed the previous logging system from the crawler service
* Simplified service behavior by removing the custom logging layer

The project now relies on standard application/container output rather than maintaining a separate custom logging subsystem. The logging removal was committed as `08417b9`.

---

## [2026-09-04]

### Fixed

* Fixed Docker Compose configuration issues
* Corrected production environment-variable propagation
* Improved container deployment consistency

### Changed

* Moved runtime configuration into the `.env/.env.prod` deployment file
* Updated Compose configuration to propagate service environment variables explicitly
* Kept the service attached to the external `crawlers-network`

The production Compose configuration publishes the configured `${PORT}` and uses the external `crawlers-network` deployment model.

---

## [2026-09-04]

### Added

* Added explicit service environment variables to Docker Compose
* Added configurable host and port settings
* Added configurable crawler concurrency
* Added configurable request timeout values
* Added healthcheck configuration
* Added persistent log-volume configuration while the logging system was still present

---

## [2026-09-04]

### Changed

* Reduced test intensity for faster development feedback
* Separated live/provider-dependent behavior from deterministic service tests
* Improved debugging around crawler and API failures

---

## [2026-09-04]

### Added

* Added the separated `Pair` domain model
* Moved pair validation away from generic request dictionaries
* Added explicit fields for:

```text
chain_id
dex_id
pair_address
quote_token_address
candles_amount
charts_resolution
```

### Changed

* Refactored crawler input around the `Pair` model
* Reduced provider-specific information leaking into the API layer

The current repository keeps `Pair` as the main normalized input model for chart requests.

---

## [2026-09-04]

### Added

* Added a four-endpoint FastAPI service
* Added:

```text
GET /health
GET /ready
POST /v1/charts
WS /v1/ws/charts
```

### Added

* Added Pydantic API request validation
* Added Pydantic response validation
* Added service-level timeout handling
* Added concurrency limiting through `asyncio.Semaphore`
* Added REST error normalization
* Added WebSocket error normalization
* Added crawler lifecycle management

The current API still exposes both the complete REST interface and the incremental WebSocket interface.

---

## [2026-09-04]

### Added

* Added the initial asynchronous DexScreener crawler
* Added binary chart-response parsing
* Added normalized candle generation
* Added quote-token-aware chart requests
* Added configurable chart resolution
* Added configurable candle counts
* Added optional proxy support
* Added timeout-aware asynchronous crawling

---

## [2026-09-04]

### Added

* Added the crawler `items` package
* Added typed candle models
* Added typed pair models
* Added API request and response schemas
* Added utility functions for chart routing and service behavior

---

## [2026-09-04]

### Added

* Added Docker support
* Added Docker Compose deployment
* Added container startup through Uvicorn
* Added `tini` as the container init process

---

## [Initial Release]

### Added

* Initial repository structure
* Initial dependency configuration
* Initial DexScreener crawler implementation
* Initial chart parser
* Initial typed data models
* Initial FastAPI service
* Initial tests
* Initial Dockerization

---

## Current architecture

The project has evolved from a DexScreener-specific chart service into a provider-oriented market-data microservice.

Current architecture:

```text
                    FastAPI
                       |
                ChartRequest
                       |
                Crawler selector
                 /           \
                /             \
       DexScreener             Birdeye
           |                      |
 Binary chart parser          OHLCV parser
           |                      |
           v                      v
 DexscreenerCandle          BirdeyeCandle
           \                      /
            \                    /
             +------ API -------+
```

The core design principle is that provider-specific behavior remains inside its crawler rather than leaking into consumer applications.

## Versioning

No stable semantic version has been released yet.

Until the first tagged release:

```text
Unreleased
```

is used for forward development, while dated sections record the historical implementation changes.

Future releases should follow:

```text
MAJOR.MINOR.PATCH
```

with:

* `MAJOR` for incompatible API or model changes
* `MINOR` for backward-compatible features
* `PATCH` for backward-compatible fixes

## References

* Repository architecture
* Provider crawler implementations
* API schemas
* Candle models
* Parser implementation
* Docker deployment
* Test suite
* Dependency lockfile

The repository's current `master` branch contains 34 commits and the latest recorded changes are from September 9, 2026.
