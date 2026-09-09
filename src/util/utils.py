ROUTES: dict[tuple, str] = {
    ("solana", "pumpswap"): "pumpfundex",
    ("solana", "pumpfun"): "pumpfundex",
    ("solana", "raydium"): "solamm",
    ("solana", "meteora"): "meteora",
    ("base", "uniswap"): "uniswapv4",
    ("robinhood", "uniswap"): "uniswapv4",
}


BIRDEYE_ROUTES = frozenset({
    "solana",
    "base",
    "bsc",
    "ethereum",
    "monad",
    "fogo",
    "mantle",
    "hyperevm",
    "megaeth",
    "robinhood",
})
