import asyncio
import os
import time
from typing import Any, AsyncGenerator, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect

from src.crawler.dexscreener import DexscreenerCrawler
from src.items import Candle, ChartRequest, ChartResponse


HOST: str = os.getenv("HOST", "0.0.0.0")
PORT: int = int(os.getenv("PORT", "9098"))

MAX_CONCURRENT_CRAWLS: int = int(os.getenv("MAX_CONCURRENT_CRAWLS", "2"))
DEFAULT_TIMEOUT_SECONDS: int = int(os.getenv("DEFAULT_TIMEOUT_SECONDS", "120"))
MAX_TIMEOUT_SECONDS: int = int(os.getenv("MAX_TIMEOUT_SECONDS", "600"))
WEBSOCKET_RECEIVE_TIMEOUT_SECONDS: int = int(os.getenv("WEBSOCKET_RECEIVE_TIMEOUT_SECONDS", "30"))
WEBSOCKET_IDLE_TIMEOUT_SECONDS: int = int(os.getenv("WEBSOCKET_IDLE_TIMEOUT_SECONDS", "600"))

crawl_gate = asyncio.Semaphore(MAX_CONCURRENT_CRAWLS)

app = FastAPI(
    title="DexScreener Charts Crawler",
    version="1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


def _normalize_timeout(timeout_seconds: Optional[int]) -> int:
    """ Normalize and validate a chart crawl timeout """
    timeout: int = timeout_seconds or DEFAULT_TIMEOUT_SECONDS

    if timeout < 1:
        raise HTTPException(
            status_code=422,
            detail="timeout_seconds must be greater than zero",
        )

    if timeout > MAX_TIMEOUT_SECONDS:
        raise HTTPException(
            status_code=422,
            detail=f"timeout_seconds cannot exceed {MAX_TIMEOUT_SECONDS}",
        )

    return timeout


async def _crawl_request(req: ChartRequest) -> AsyncGenerator[Candle, None]:
    """ Crawl a pair chart with the configured concurrency and timeout limits """
    timeout_seconds: int = _normalize_timeout(req.timeout_seconds)

    async with crawl_gate:
        crawler = DexscreenerCrawler(proxy=req.proxy)
        generator: AsyncGenerator = crawler.crawl_charts(req.pair)
        deadline: float = time.monotonic() + timeout_seconds

        while True:
            remaining: float = deadline - time.monotonic()

            if remaining <= 0:
                raise TimeoutError("chart crawl operation timed out")

            try:
                candle: Candle = await asyncio.wait_for(
                    generator.__anext__(),
                    timeout=remaining,
                )
            except StopAsyncIteration:
                break

            yield candle


async def _collect(generator: AsyncGenerator[Candle, None]) -> list[Candle]:
    """ Collect chart candles from an async generator """
    return [candle async for candle in generator]


async def _send_error(
    websocket: WebSocket,
    status_code: int,
    detail: str,
) -> None:
    """ Send a normalized WebSocket error response """
    await websocket.send_json({
        "type": "error",
        "status_code": status_code,
        "detail": detail,
    })


async def _stream(
    websocket: WebSocket,
    generator: AsyncGenerator[Candle, None],
) -> int:
    """ Stream chart candles to a WebSocket client """
    count = 0

    async for candle in generator:
        await websocket.send_json({
            "type": "item",
            "data": candle.model_dump(mode="json"),
        })

        count += 1

    await websocket.send_json({
        "type": "done",
        "count": count,
    })

    return count


@app.get("/health")
async def health() -> dict[str, Any]:
    """ Return the liveness state of the service """
    return {
        "status": "healthy",
        "service": "dexscreener-charts-crawler",
        "version": app.version,
    }


@app.get("/ready")
async def ready() -> dict[str, Any]:
    """ Return whether the service is ready to accept crawl requests """
    return {
        "status": "ready",
        "host": HOST,
        "port": PORT,
        "available_slots": crawl_gate._value,
        "max_concurrent_crawls": MAX_CONCURRENT_CRAWLS,
        "default_timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
        "max_timeout_seconds": MAX_TIMEOUT_SECONDS,
    }


@app.post("/v1/charts", response_model=ChartResponse)
async def charts(req: ChartRequest) -> ChartResponse:
    """ Crawl and return all parsed chart candles for a pair """
    started = time.perf_counter()

    try: candles = await _collect(_crawl_request(req))

    except TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc

    elapsed_ms = int((time.perf_counter() - started) * 1000)

    return ChartResponse(
        pair=req.pair,
        count=len(candles),
        elapsed_ms=elapsed_ms,
        charts=candles,
    )


@app.websocket("/v1/ws/charts")
async def websocket_charts(websocket: WebSocket) -> None:
    """ Stream parsed chart candles over WebSocket """
    await websocket.accept()

    try:
        payload: dict[str, Any] = await asyncio.wait_for(
            websocket.receive_json(),
            timeout=WEBSOCKET_RECEIVE_TIMEOUT_SECONDS,
        )

        req = ChartRequest.model_validate(payload)
        timeout_seconds: int = _normalize_timeout(req.timeout_seconds)

        await asyncio.wait_for(
            _stream(
                websocket,
                _crawl_request(req),
            ),
            timeout=min(
                timeout_seconds,
                WEBSOCKET_IDLE_TIMEOUT_SECONDS,
            ),
        )

    except asyncio.TimeoutError:
        await _send_error(
            websocket,
            504,
            "websocket or chart crawl operation timed out",
        )

    except WebSocketDisconnect:
        return

    except ValueError as exc:
        await _send_error(
            websocket,
            422,
            str(exc),
        )

    except Exception as exc:
        await _send_error(
            websocket,
            500,
            str(exc),
        )

    finally:
        try: await websocket.close()
        except Exception: pass


if __name__ == "__main__":
    uvicorn.run(
        "src.api:app",
        host=HOST,
        port=PORT,
        reload=False,
    )
