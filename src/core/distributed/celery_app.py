"""Celery worker configuration and process initialization for CareerGraph AI."""

import os
from typing import Any, Callable, Dict, Optional
from src.core.db.dual_engine import (
    init_dual_database_pool,
    get_checkpoint_db_path,
    get_telemetry_db_path,
)

# Durability and concurrency defaults
DEFAULT_CELERY_CONFIG: Dict[str, Any] = {
    "task_acks_late": True,
    "task_reject_on_worker_lost": True,
    "worker_prefetch_multiplier": 1,
    "broker_url": os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    "result_backend": os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
    "task_serializer": "json",
    "result_serializer": "json",
    "accept_content": ["json"],
    "timezone": "UTC",
    "enable_utc": True,
    "task_default_queue": "careergraph_tasks",
}


class ConfigNamespace(dict):
    """Configuration namespace supporting both dict keys and attribute access."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'ConfigNamespace' object has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value

    def update(self, *args: Any, **kwargs: Any) -> None:
        super().update(*args, **kwargs)


class SimulatedAsyncResult:
    """Lightweight simulation of Celery's AsyncResult for testing and standalone mode."""

    def __init__(self, task_id: str, result: Any, status: str = "SUCCESS"):
        self.id = task_id
        self.task_id = task_id
        self.result = result
        self.status = status

    def get(self, timeout: Optional[float] = None) -> Any:
        return self.result

    def successful(self) -> bool:
        return self.status == "SUCCESS"

    def ready(self) -> bool:
        return True


class SimulatedCeleryApp:
    """Lightweight Celery App compatible interface when Celery is simulated."""

    def __init__(self, main: str = "careergraph_ai", conf: Optional[Dict[str, Any]] = None):
        self.main = main
        self.conf = ConfigNamespace(DEFAULT_CELERY_CONFIG)
        if conf:
            self.conf.update(conf)
        self.tasks: Dict[str, Callable[..., Any]] = {}

    def task(self, *args: Any, **opts: Any) -> Callable[..., Any]:
        """Decorator to register a function as a Celery task with .delay() and .apply_async() capabilities."""
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            name = opts.get("name", f"{fn.__module__}.{fn.__name__}")

            def delay(*call_args: Any, **call_kwargs: Any) -> SimulatedAsyncResult:
                res = fn(*call_args, **call_kwargs)
                import uuid
                return SimulatedAsyncResult(task_id=f"task_{uuid.uuid4().hex[:8]}", result=res)

            def apply_async(args: Optional[tuple] = None, kwargs: Optional[dict] = None, **kw: Any) -> SimulatedAsyncResult:
                call_args = args or ()
                call_kwargs = kwargs or {}
                res = fn(*call_args, **call_kwargs)
                import uuid
                return SimulatedAsyncResult(task_id=f"task_{uuid.uuid4().hex[:8]}", result=res)

            setattr(fn, "delay", delay)
            setattr(fn, "apply_async", apply_async)
            self.tasks[name] = fn
            return fn

        if len(args) == 1 and callable(args[0]):
            return decorator(args[0])
        return decorator

    def send_task(self, name: str, args: Optional[tuple] = None, kwargs: Optional[dict] = None, **opts: Any) -> SimulatedAsyncResult:
        if name in self.tasks:
            fn = self.tasks[name]
            res = fn(*(args or ()), **(kwargs or {}))
            import uuid
            return SimulatedAsyncResult(task_id=f"task_{uuid.uuid4().hex[:8]}", result=res)
        import uuid
        return SimulatedAsyncResult(task_id=f"task_{uuid.uuid4().hex[:8]}", result=None, status="PENDING")


def on_worker_process_init(
    checkpoints_path: Optional[str] = None,
    telemetry_path: Optional[str] = None,
    **kwargs: Any,
) -> None:
    """
    Signal handler for worker process initialization.
    Re-initializes the dual SQLite database pool to ensure connection and WAL handle
    isolation across worker processes.
    """
    cp_path = checkpoints_path or get_checkpoint_db_path()
    tel_path = telemetry_path or get_telemetry_db_path()
    init_dual_database_pool(checkpoints_path=cp_path, telemetry_path=tel_path)


# Create and configure the global celery_app instance
try:
    from celery import Celery
    from celery.signals import worker_process_init

    celery_app = Celery("careergraph_ai")
    celery_app.conf.update(DEFAULT_CELERY_CONFIG)

    @worker_process_init.connect
    def _celery_worker_process_init(*args: Any, **kwargs: Any) -> None:
        on_worker_process_init()

except ImportError:
    celery_app = SimulatedCeleryApp("careergraph_ai")
