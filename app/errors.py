from fastapi import HTTPException


ERROR_STATUS = {
    "INVALID_REQUEST": 400, "AUTHENTICATION_REQUIRED": 401, "PERMISSION_DENIED": 403,
    "RESOURCE_NOT_FOUND": 404, "VERSION_CONFLICT": 409, "INVALID_STATE_TRANSITION": 409,
    "FILE_TOO_LARGE": 413, "UNSUPPORTED_MEDIA_TYPE": 415, "HASH_MISMATCH": 422,
    "AI_RETRY_LIMIT_REACHED": 429, "AI_PROVIDER_UNAVAILABLE": 503,
}


class AppError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def http_error(error: AppError) -> HTTPException:
    return HTTPException(ERROR_STATUS[error.code], {"code": error.code, "message": error.message})
