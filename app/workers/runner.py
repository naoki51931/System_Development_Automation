import argparse, os, socket, time
from app.core.config import get_settings
from app.db.session import create_database_engine, create_session_factory
from app.workers.outbox import claim, complete, fail

def run_once(factory, worker_id: str) -> bool:
    with factory.begin() as session:
        job = claim(session, worker_id)
        if not job: return False
        try:
            # Local dispatch records completion only; provider-specific handlers are mocks.
            complete(session, job)
        except Exception:
            fail(session, job, "LOCAL_HANDLER_FAILED")
        return True

def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--once", action="store_true"); parser.add_argument("--interval", type=float, default=2); args = parser.parse_args()
    factory = create_session_factory(create_database_engine(get_settings())); worker_id = f"{socket.gethostname()}:{os.getpid()}"
    while True:
        worked = run_once(factory, worker_id)
        if args.once: break
        if not worked: time.sleep(args.interval)
if __name__ == "__main__": main()
