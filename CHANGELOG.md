# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Added a FastAPI microservice for collecting DexScreener market and chart data.
- Added a health endpoint at `GET /health` for basic service liveness checks.
- Added a readiness endpoint at `GET /ready` for dependency/readiness checks.
- Added a REST chart collection endpoint at `POST /v1/charts`.
- Added a WebSocket chart collection endpoint at `WS /v1/ws/charts` for streaming chart collection requests/results.
- Added Pydantic request/response validation for the public API.
- Added support for DexScreener chart retrieval and binary chart-data parsing used by the backtesting collector.
- Added asynchronous HTTP handling for DexScreener requests.
- Added crawler execution and resource-management support for the chart collection workflow.
- Added Docker support for running the service as a standalone container.
- Added Docker Compose configuration for local/service deployment.
- Added pytest configuration with automatic asyncio support.
- Added development dependencies for API and asynchronous test coverage.

### Changed

- Established `/v1` as the versioned namespace for application endpoints.
- Separated liveness (`/health`) from readiness (`/ready`) checks to better support container orchestration and service monitoring.
- Standardized chart collection behind both synchronous HTTP and long-lived WebSocket interfaces.
- Standardized the project on Python `>=3.12,<3.13`.
- Added explicit dependency version ranges for FastAPI, HTTPX, Pydantic, SeleniumBase, Uvicorn, and related packages.

### Fixed

- Improved handling of chart-collection failures so API clients can receive structured errors instead of relying on crawler-level exceptions.
- Improved service startup/readiness behavior for deployments where crawler dependencies are not immediately available.
- Improved validation of malformed chart requests before starting crawler work.

### Documentation

- Added detailed service documentation covering installation, configuration, Docker usage, architecture, and troubleshooting.
- Documented all four public endpoints with request/response examples.
- Documented REST and WebSocket usage patterns and message flows.

### Testing

- Added test infrastructure for asynchronous FastAPI endpoints.
- Added coverage for API health/readiness behavior and chart collection interfaces.
- Added project-level pytest configuration so asynchronous tests can be run directly through standard pytest tooling.

### Notes

- No stable release version has been published yet. All changes currently belong under `Unreleased` until the first tagged release is created.
