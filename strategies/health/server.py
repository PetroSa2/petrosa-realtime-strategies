"""
Health check server for the Petrosa Realtime Strategies service.

This module provides health check endpoints and monitoring capabilities
for Kubernetes liveness and readiness probes, plus configuration API.
"""

import asyncio
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, Optional

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

import constants
from strategies.api.config_routes import (
    router as config_router,
    set_config_manager,
)
from strategies.api.metrics_routes import (
    router as metrics_router,
    set_depth_analyzer,
)

# Prometheus metrics
STRATEGY_SIGNALS_GENERATED = Counter(
    "strategy_signals_generated_total",
    "Total signals generated",
    ["strategy", "signal_type"],
)
NATS_MESSAGES_CONSUMED = Counter(
    "nats_messages_consumed_total", "Total NATS messages consumed"
)
NATS_MESSAGES_PUBLISHED = Counter(
    "nats_messages_published_total", "Total orders published to NATS"
)
STRATEGY_PROCESSING_TIME = Histogram(
    "strategy_processing_time_seconds", "Time to process a message", ["strategy"]
)
STRATEGY_ERRORS = Counter(
    "strategy_errors_total", "Total strategy errors", ["strategy", "error_type"]
)
CIRCUIT_BREAKER_STATE = Gauge(
    "circuit_breaker_state", "Circuit breaker state (0=closed, 1=open)", ["component"]
)
MEMORY_USAGE_BYTES = Gauge("memory_usage_bytes", "Memory usage in bytes")
CPU_USAGE_PERCENT = Gauge("cpu_usage_percent", "CPU usage percentage")
SERVICE_UPTIME = Gauge("service_uptime_seconds", "Service uptime in seconds")
ENABLED_STRATEGIES_COUNT = Gauge(
    "enabled_strategies_count", "Number of enabled strategies"
)


class HealthServer:
    """Health check server for monitoring service health."""

    def __init__(
        self,
        port: int = 8080,
        logger: Optional[structlog.BoundLogger] = None,
        consumer=None,
        publisher=None,
        heartbeat_manager=None,
        config_manager=None,
        depth_analyzer=None,
    ):
        """Initialize the health server."""
        self.port = port
        self.logger = logger or structlog.get_logger()
        self.consumer = consumer
        self.publisher = publisher
        self.heartbeat_manager = heartbeat_manager
        self.config_manager = config_manager
        self.depth_analyzer = depth_analyzer

        # Create lifespan for OTLP handler attachment
        @asynccontextmanager
        async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
            """Application lifespan manager - attach OTLP logging handler and set config manager"""
            # Startup: Attach OTLP handler after uvicorn configures logging
            try:
                from petrosa_otel import attach_logging_handler

                attach_logging_handler()
            except Exception as e:
                self.logger.warning(f"Failed to attach OTLP logging handler: {e}")

            # Set config manager for API routes if available
            if self.config_manager:
                set_config_manager(self.config_manager)
                self.logger.info("✅ Configuration manager set for API routes")
            else:
                self.logger.warning(
                    "⚠️  No configuration manager provided - Config API routes will be unavailable"
                )

            # Set depth analyzer for metrics routes if available
            if self.depth_analyzer:
                set_depth_analyzer(self.depth_analyzer)
                self.logger.info("✅ Depth analyzer set for metrics API routes")
            else:
                self.logger.warning(
                    "⚠️  No depth analyzer provided - Metrics API routes will be unavailable"
                )

            yield

            # Shutdown: Nothing to clean up

        # FastAPI app with lifespan
        self.app = FastAPI(
            title="Petrosa Realtime Strategies",
            description="Health check and configuration API for the trading signal service",
            version=constants.SERVICE_VERSION,
            lifespan=lifespan,
        )

        # Instrument FastAPI for OpenTelemetry tracing
        try:
            from petrosa_otel.instrumentors import instrument_fastapi

            instrument_fastapi(self.app)
            self.logger.info("✅ FastAPI instrumented for OpenTelemetry tracing")
        except Exception as e:
            self.logger.warning(f"⚠️  Failed to instrument FastAPI: {e}")

        # Include configuration API router
        self.app.include_router(config_router)
        self.logger.info("✅ Configuration API routes registered")

        # Include market metrics API router
        self.app.include_router(metrics_router)
        self.logger.info("✅ Market metrics API routes registered")

        # Server state
        self.server = None
        self.is_running = False
        self.start_time = None

        # Health check state
        self.health_status = {
            "status": "healthy",
            "timestamp": None,
            "uptime_seconds": 0,
            "version": constants.SERVICE_VERSION,
            "environment": constants.ENVIRONMENT,
        }

        # Register routes
        self._register_routes()

    def _register_routes(self) -> None:
        """Register FastAPI routes."""

        @self.app.get("/healthz")
        async def health_check():
            """Liveness probe endpoint."""
            return await self._get_health_status()

        @self.app.get("/ready")
        async def readiness_check():
            """Readiness probe endpoint."""
            return await self._get_readiness_status()

        @self.app.get("/metrics")
        async def metrics():
            """Prometheus metrics endpoint."""
            return await self._get_prometheus_metrics()

        @self.app.get("/info")
        async def info():
            """Service information endpoint."""
            return await self._get_service_info()

        @self.app.get("/")
        async def root():
            """Root endpoint."""
            return {
                "service": constants.SERVICE_NAME,
                "version": constants.SERVICE_VERSION,
                "status": "running",
                "endpoints": {
                    "health": "/healthz",
                    "readiness": "/ready",
                    "metrics": "/metrics",
                    "info": "/info",
                    "configuration_api": "/api/v1/strategies",
                    "api_docs": "/docs",
                    "openapi_spec": "/openapi.json",
                },
            }

    async def start(self) -> None:
        """Start the health server."""
        self.logger.info(f"Starting health server on port {self.port}")

        try:
            # Start the server
            config = uvicorn.Config(
                app=self.app,
                host="0.0.0.0",
                port=self.port,
                log_level="info",
                access_log=False,
            )
            self.server = uvicorn.Server(config)

            # Start server in background
            self.is_running = True
            self.start_time = time.time()

            # Run server in background task
            asyncio.create_task(self._run_server())

            self.logger.info(f"Health server started on port {self.port}")

        except Exception as e:
            self.logger.error(f"Failed to start health server: {e}")
            raise

    async def stop(self) -> None:
        """Stop the health server."""
        self.logger.info("Stopping health server")

        self.is_running = False

        if self.server:
            self.server.should_exit = True
            self.logger.info("Health server stopped")

    async def _run_server(self) -> None:
        """Run the server in background."""
        try:
            await self.server.serve()
        except Exception as e:
            self.logger.error(f"Health server error: {e}")

    async def _get_health_status(self) -> dict[str, Any]:
        """Get health status for liveness probe."""
        try:
            # Update uptime
            if self.start_time:
                uptime = time.time() - self.start_time
            else:
                uptime = 0

            # Basic health checks - only check essential conditions
            health_checks = {
                "server_running": self.is_running,
                "uptime_seconds": uptime >= 0,  # Just check if uptime is valid
                "memory_usage": self._get_memory_usage()
                >= 0,  # Just check if memory is valid
                "cpu_usage": self._get_cpu_usage() >= 0,  # Just check if CPU is valid
            }

            # Determine overall health - only check server running
            is_healthy = self.is_running

            status = {
                "status": "healthy" if is_healthy else "unhealthy",
                "timestamp": time.time(),
                "uptime_seconds": uptime,
                "checks": health_checks,
                "version": constants.SERVICE_VERSION,
                "environment": constants.ENVIRONMENT,
            }

            # Update health status
            self.health_status.update(status)

            if not is_healthy:
                raise HTTPException(status_code=503, detail="Service unhealthy")

            return status

        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            raise HTTPException(status_code=503, detail=f"Health check failed: {e}")

    async def _get_readiness_status(self) -> dict[str, Any]:
        """Get readiness status for readiness probe."""
        try:
            # Get health status first
            health_status = await self._get_health_status()

            # Additional readiness checks
            readiness_checks = {
                "health_status": health_status["status"] == "healthy",
                "configuration_loaded": True,  # Add more checks as needed
                "dependencies_available": True,  # Add more checks as needed
            }

            # Determine readiness
            is_ready = all(readiness_checks.values())

            status = {
                "ready": is_ready,
                "timestamp": time.time(),
                "checks": readiness_checks,
                "health_status": health_status,
            }

            if not is_ready:
                raise HTTPException(status_code=503, detail="Service not ready")

            return status

        except Exception as e:
            self.logger.error(f"Readiness check failed: {e}")
            raise HTTPException(status_code=503, detail=f"Readiness check failed: {e}")

    async def _get_prometheus_metrics(self) -> Response:
        """Get Prometheus-format metrics."""
        try:
            # Update gauge metrics with current values
            if self.start_time:
                uptime = time.time() - self.start_time
                SERVICE_UPTIME.set(uptime)

            memory_mb = self._get_memory_usage()
            MEMORY_USAGE_BYTES.set(memory_mb * 1024 * 1024)  # Convert MB to bytes

            cpu = self._get_cpu_usage()
            CPU_USAGE_PERCENT.set(cpu)

            # Update enabled strategies count
            enabled_strategies = constants.get_enabled_strategies()
            ENABLED_STRATEGIES_COUNT.set(len(enabled_strategies))

            # Update component metrics (circuit breakers)
            components = self._get_component_metrics()
            for component_name, component_data in components.items():
                if isinstance(component_data, dict):
                    # Update circuit breaker state
                    cb_state = component_data.get("circuit_breaker_state", "CLOSED")
                    CIRCUIT_BREAKER_STATE.labels(component=component_name).set(
                        1 if cb_state == "OPEN" else 0
                    )

            # Generate Prometheus-format metrics
            metrics_output = generate_latest()

            return Response(
                content=metrics_output, media_type=CONTENT_TYPE_LATEST, status_code=200
            )

        except Exception as e:
            self.logger.error(f"Failed to generate Prometheus metrics: {e}")
            return Response(
                content=f"# Error generating metrics: {e}\n", status_code=500
            )

    async def _get_metrics(self) -> dict[str, Any]:
        """Get service metrics."""
        try:
            metrics = {
                "service": {
                    "name": constants.SERVICE_NAME,
                    "version": constants.SERVICE_VERSION,
                    "environment": constants.ENVIRONMENT,
                    "uptime_seconds": (
                        time.time() - self.start_time if self.start_time else 0
                    ),
                },
                "system": {
                    "memory_usage_mb": self._get_memory_usage(),
                    "cpu_usage_percent": self._get_cpu_usage(),
                },
                "health": {
                    "status": self.health_status.get("status", "unknown"),
                    "last_check": self.health_status.get("timestamp"),
                },
                "configuration": {
                    "enabled_strategies": constants.get_enabled_strategies(),
                    "trading_symbols": constants.TRADING_SYMBOLS,
                    "enable_shorts": constants.TRADING_ENABLE_SHORTS,
                    "heartbeat_enabled": constants.HEARTBEAT_ENABLED,
                    "heartbeat_interval": constants.HEARTBEAT_INTERVAL_SECONDS,
                },
                "components": self._get_component_metrics(),
            }

            return metrics

        except Exception as e:
            self.logger.error(f"Failed to get metrics: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get metrics: {e}")

    async def _get_service_info(self) -> dict[str, Any]:
        """Get service information."""
        try:
            info = {
                "service": {
                    "name": constants.SERVICE_NAME,
                    "version": constants.SERVICE_VERSION,
                    "description": "Stateless trading signal service for real-time market data processing",
                },
                "environment": {
                    "environment": constants.ENVIRONMENT,
                    "log_level": constants.LOG_LEVEL,
                    "enable_otel": constants.ENABLE_OTEL,
                },
                "configuration": {
                    "nats_url": constants.NATS_URL,
                    "consumer_topic": constants.NATS_CONSUMER_TOPIC,
                    "publisher_topic": constants.NATS_PUBLISHER_TOPIC,
                    "health_check_port": constants.HEALTH_CHECK_PORT,
                },
                "strategies": {
                    "enabled": constants.get_enabled_strategies(),
                    "config": constants.get_strategy_config(),
                },
                "trading": {
                    "symbols": constants.TRADING_SYMBOLS,
                    "enable_shorts": constants.TRADING_ENABLE_SHORTS,
                    "leverage": constants.TRADING_LEVERAGE,
                    "config": constants.get_trading_config(),
                },
                "risk": {
                    "config": constants.get_risk_config(),
                },
            }

            return info

        except Exception as e:
            self.logger.error(f"Failed to get service info: {e}")
            raise HTTPException(
                status_code=500, detail=f"Failed to get service info: {e}"
            )

    def _get_memory_usage(self) -> float:
        """Get memory usage in MB."""
        try:
            import psutil

            process = psutil.Process()
            memory_info = process.memory_info()
            return memory_info.rss / 1024 / 1024  # Convert to MB
        except ImportError:
            return 0.0
        except Exception:
            return 0.0

    def _get_cpu_usage(self) -> float:
        """Get CPU usage percentage."""
        try:
            import psutil

            process = psutil.Process()
            return process.cpu_percent()
        except ImportError:
            return 0.0
        except Exception:
            return 0.0

    def update_health_status(self, status: dict[str, Any]) -> None:
        """Update health status with external information."""
        self.health_status.update(status)

    def get_health_status(self) -> dict[str, Any]:
        """Get current health status."""
        return self.health_status.copy()

    def is_healthy(self) -> bool:
        """Check if the service is healthy."""
        return self.health_status.get("status") == "healthy"

    def _get_component_metrics(self) -> dict[str, Any]:
        """Get metrics from all service components."""
        components = {}

        # Consumer metrics
        if self.consumer:
            try:
                components["consumer"] = self.consumer.get_metrics()
                components["consumer"]["health"] = self.consumer.get_health_status()
            except Exception as e:
                components["consumer"] = {"error": str(e)}

        # Publisher metrics
        if self.publisher:
            try:
                components["publisher"] = self.publisher.get_metrics()
                components["publisher"]["health"] = self.publisher.get_health_status()
            except Exception as e:
                components["publisher"] = {"error": str(e)}

        # Heartbeat manager metrics
        if self.heartbeat_manager:
            try:
                components["heartbeat"] = self.heartbeat_manager.get_heartbeat_status()
            except Exception as e:
                components["heartbeat"] = {"error": str(e)}

        return components
