import struct
import datetime as dt

from typing import Generator

from src.items.charts import Candle


def _read_string(data, offset: int) -> tuple[str, int]:
    """
    Parse a DexScreener encoded decimal string from binary payload data

    The function reads a numeric string from the provided byte payload,
    validates that every byte represents a supported numeric character,
    and returns the decoded ASCII value together with the next byte offset

    Args:
        data (bytes): Raw DexScreener binary payload containing the encoded decimal value
        offset (int): Byte position where the encoded decimal string starts

    Returns:
        tuple[str, int]:
            A tuple containing:
                str: Decoded ASCII decimal string
                int: Byte offset immediately after the decoded string

    Raises:
        ValueError:
            If the payload ends unexpectedly, the encoded length is missing,
            the string exceeds the payload boundary, or the value contains
            unsupported characters
       """
    if offset >= len(data):
        raise ValueError("unexpected end of data")

    if data[offset] == 2:
        offset += 1

    if offset >= len(data):
        raise ValueError("missing string length")

    length = data[offset] >> 1
    offset += 1

    end = offset + length
    if end > len(data):
        raise ValueError("string exceeds payload")

    value = data[offset:end]
    for byte in value:
        is_digit = 48 <= byte <= 57
        is_decimal = byte == 46
        is_negative = byte == 45

        if not (is_digit or is_decimal or is_negative):
            raise ValueError(f"invalid numeric field: {value!r}")

    return value.decode("ascii"), end


def parse_dexscreener_bars(data: bytes) -> Generator[Candle, None, None]:
    """
    Parse DexScreener binary chart candles into normalized candle dictionaries

    The function scans the binary DexScreener chart payload for candle
    timestamps, reads the nine encoded numeric values associated with each
    candle, validates OHLC relationships, and returns valid candles in a
    normalized dictionary format

    Args:
        data (bytes): Raw binary response returned by the DexScreener chart endpoint

    Returns:
        list[dict[str, Any]]: A list of parsed candle dictionaries containing:
            timestamp (int): Candle timestamp in milliseconds
            dt (str): Candle timestamp converted to an ISO 8601 UTC datetime string
            open (float): Opening price
            openUsd (float): Opening price in USD
            high (float): Highest price
            highUsd (float): Highest price in USD
            low (float): Lowest price
            lowUsd (float): Lowest price in USD
            close (float): Closing price
            closeUsd (float): Closing price in USD
            volumeUsd (float): Candle trading volume in USD
    Raises:
        TypeError: If data is not a bytes object
        ValueError: If no DexScreener candle timestamp markers are found in the payload
    """
    if not isinstance(data, bytes):
        raise TypeError(f"expected bytes, got {type(data).__name__}")

    marker: bytes = b"zB"
    positions: list[int] = []
    start: int = 0

    while True:
        position: int = data.find(marker, start)
        if position == -1: break

        positions.append(position)
        start = position + 1

    if not positions:
        raise ValueError("no DexScreener candle timestamps found")

    for marker_position in positions:
        timestamp_start = marker_position - 6
        if timestamp_start < 0: continue

        timestamp: int = int(struct.unpack("<d", data[timestamp_start:marker_position + 2])[0])
        timestamp_dt: dt.datetime = dt.datetime.fromtimestamp(timestamp / 1000, tz=dt.timezone.utc)

        offset: int = marker_position + 2
        values: list[float] = []
        try:
            for _ in range(9):
                value, offset = _read_string(data, offset)
                values.append(float(value))
        except ValueError:
            continue

        if len(values) != 9:
            continue

        (
            open_value,
            open_usd,
            high_value,
            high_usd,
            low_value,
            low_usd,
            close_value,
            close_usd,
            volume_usd,
        ) = values

        if high_value < max(open_value, close_value): continue
        if low_value > min(open_value, close_value): continue
        if high_usd < max(open_usd, close_usd): continue
        if low_usd > min(open_usd, close_usd): continue

        yield Candle(
            timestamp=timestamp,
            datetime=timestamp_dt.isoformat(),
            open=open_value,
            open_usd=open_usd,
            high=high_value,
            high_usd=high_usd,
            low=low_value,
            low_usd=low_usd,
            close=close_value,
            close_usd=close_usd,
            volume_usd=volume_usd,
        )
