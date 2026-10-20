"""Menu and drive-thru ordering server."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.orders import OrderError
from app.routers import catalog, orders

app = FastAPI(
    title="Menu server", description="McDonald's Nemi Nagar, Jaipur: menu and drive-thru orders"
)
app.include_router(catalog.router)
app.include_router(orders.router)
app.mount(
    "/images",
    StaticFiles(directory=Path(__file__).resolve().parent.parent / "static" / "images"),
    name="images",
)


@app.exception_handler(OrderError)
def order_error(_: Request, error: OrderError) -> JSONResponse:
    return JSONResponse({"detail": error.detail}, status_code=error.status)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
