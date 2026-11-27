"""Định dạng lỗi chung: {"error": {"code", "message", "details"}}."""
from __future__ import annotations

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details=None, headers: dict | None = None):
        self.status, self.code, self.message, self.details, self.headers = status, code, message, details, headers


def _body(code: str, message: str, details=None) -> dict:
    return {"error": {"code": code, "message": message, "details": details}}


def install(app) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, e: ApiError):
        return JSONResponse(_body(e.code, e.message, e.details), status_code=e.status, headers=e.headers)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, e: StarletteHTTPException):
        # Đường dẫn trang không tồn tại: trả trang "Không tìm thấy" có đủ menu thay vì chữ JSON thô.
        # API (/v1/...) giữ định dạng JSON chung.
        if e.status_code == 404 and not request.url.path.startswith("/v1/"):
            from ..site.routes import _not_found
            return _not_found(request, "Trang bạn tìm không tồn tại hoặc đã được chuyển đi.")
        codes = {404: ("not_found", "Không tìm thấy"), 405: ("method_not_allowed", "Phương thức không được hỗ trợ")}
        code, msg = codes.get(e.status_code, ("http_error", str(e.detail)))
        return JSONResponse(_body(code, msg), status_code=e.status_code,
                            headers=getattr(e, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, e: RequestValidationError):
        details = [{"loc": list(x.get("loc", [])), "msg": x.get("msg")} for x in e.errors()]
        return JSONResponse(_body("invalid_param", "Tham số không hợp lệ", details), status_code=400)
