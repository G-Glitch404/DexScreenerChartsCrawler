from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.util.utils import ROUTES


class Pair(BaseModel):
    """
    Validate and normalize the trade information required to request DexScreener charts

    Args:
        chain_id (str): Blockchain identifier used by DexScreener
        dex_id (str): Decentralized exchange identifier used by DexScreener
        pair_address (str): Trading pair contract address
        quote_token_address (str): Quote token contract address
        candles_amount (int): Maximum number of candles requested
        charts_resolution (int): Chart resolution in minutes

    Returns:
        Trade: Validated trade request model
    """
    model_config = ConfigDict(extra="forbid")

    chain_id: str = Field(min_length=1, max_length=64)
    dex_id: str = Field(min_length=1, max_length=64)
    pair_address: str = Field(min_length=1, max_length=256)
    quote_token_address: str = Field(min_length=1, max_length=256)
    candles_amount: int = Field(default=329, ge=1, le=10_000)
    charts_resolution: int = Field(default=5, ge=1, le=1440)

    @field_validator("chain_id", "dex_id", "pair_address", "quote_token_address")
    @classmethod
    def normalize_strings(cls, value: str) -> str:
        """ Normalize required trade string fields """

        value = value.strip()

        if not value:
            raise ValueError("trade field cannot be empty")

        return value

    @field_validator("chain_id", "dex_id")
    @classmethod
    def normalize_identifiers(cls, value: str) -> str:
        """ Normalize DexScreener route identifiers """

        return value.lower()

    @field_validator("pair_address", "quote_token_address")
    @classmethod
    def validate_addresses(cls, value: str) -> str:
        """ Validate required DexScreener address fields """

        return value.strip()

    @model_validator(mode="after")
    def validate_route(self) -> "Pair":
        """ Validate that the requested chain and DEX route is supported """

        if (self.chain_id, self.dex_id) not in ROUTES:
            raise ValueError(f"unsupported chart route: {self.chain_id}/{self.dex_id}")

        return self
