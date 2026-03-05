from .futures import router as futures_router
from .health import router as health_router
from .indicator import router as indicator_router
from .markets import router as markets_router
from .ml import router as ml_router
from .signal import router as signal_router

__all__ = [
    "health_router",
    "futures_router",
    "indicator_router",
    "markets_router",
    "ml_router",
    "signal_router",
]
