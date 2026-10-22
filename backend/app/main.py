"""Menu and drive-thru ordering server."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.customers import router as customers
from app.menu import router as menu
from app.orders import router as orders
from app.orders.service import OrderError

app = FastAPI(
    title="Menu server", description="McDonald's Nemi Nagar, Jaipur: menu and drive-thru orders"
)
app.include_router(menu.router)
app.include_router(orders.router)
app.include_router(customers.router)
app.mount(
    "/images",
    StaticFiles(directory=Path(__file__).resolve().parent.parent / "static" / "images"),
    name="images",
)


@app.exception_handler(OrderError)
def order_error(_: Request, error: OrderError) -> JSONResponse:
    return JSONResponse({"detail": error.detail}, status_code=error.status)


@app.exception_handler(StarletteHTTPException)
def http_error(_: Request, error: StarletteHTTPException) -> JSONResponse:
    """Plain errors (an unknown id, a wrong path) get the same `code` + `message` as the rest."""
    code = "not_found" if error.status_code == 404 else "error"
    return JSONResponse(
        {"detail": {"code": code, "message": str(error.detail)}}, status_code=error.status_code
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
