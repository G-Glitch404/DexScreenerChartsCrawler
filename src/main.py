import os
import uvicorn

HOST: str = os.getenv("HOST", "0.0.0.0")
PORT: int = int(os.getenv("PORT", "9098"))


def main() -> None:
    """ Start the DexScreener charts service """
    uvicorn.run(
        "src.api:app",
        host=HOST,
        port=PORT,
        reload=False,
    )


if __name__ == "__main__":
    main()
