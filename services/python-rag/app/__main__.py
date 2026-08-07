import uvicorn

from .settings import settings


def main() -> None:
    uvicorn.run("app.main:app", host=settings.rag_host, port=settings.rag_port)


if __name__ == "__main__":
    main()
