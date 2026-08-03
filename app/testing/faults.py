import os
class InjectedFault(RuntimeError):
    def __init__(self, code:str, retryable:bool=True): self.code,self.retryable=code,retryable;super().__init__(code)
RETRYABLE={"AI_PROVIDER_TIMEOUT","PAYMENT_PROVIDER_UNAVAILABLE","EMAIL_PROVIDER_FAILURE","STORAGE_WRITE_FAILURE","DOCUMENT_RENDER_FAILURE","WORKER_CRASH_AFTER_CLAIM","DATABASE_DEADLOCK_SIMULATION"}
def active(code:str)->bool:
    if os.getenv("APP_ENV","development").lower() in {"production","prod"}: return False
    return code in {x.strip() for x in os.getenv("APP_FAULT_INJECTION","").split(",") if x.strip()}
def inject(code:str)->None:
    if active(code): raise InjectedFault(code,code in RETRYABLE)

def database_error_code(error: BaseException) -> str:
    """Classify local PostgreSQL concurrency errors without exposing SQL text."""
    sqlstate = getattr(error, "sqlstate", None) or getattr(getattr(error, "orig", None), "sqlstate", None)
    return "DATABASE_RETRYABLE" if sqlstate in {"40P01", "40001", "55P03"} else "DATABASE_FAILED"
