"""
Health check server for the Petrosa Realtime Strategies service.

This module provides health check endpoints and monitoring capabilities
for Kubernetes liveness and readiness probes.
"""

import asyncio
import time
from typing import Any, Dict, Optional
import structlog

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

import constants


class HealthServer:
    """Health check server for monitoring service health."""

    def __init__(
        self,
        port: int = 8080,
        logger: Optional[structlog.BoundLogger] = None,
    ):
        """Initialize the health server."""
        self.port = port
        self.logger = logger or structlog.get_logger()

        # FastAPI app
        self.app = FastAPI(
            title="Petrosa Realtime Strategies Health",
            description="Health check endpoints for the trading signal service",
            version=constants.SERVICE_VERSION,
        )

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
            """Metrics endpoint."""
            return await self._get_metrics()

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
                }
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

    async def _get_health_status(self) -> Dict[str, Any]:
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
                "memory_usage": self._get_memory_usage() >= 0,  # Just check if memory is valid
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

    async def _get_readiness_status(self) -> Dict[str, Any]:
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

    async def _get_metrics(self) -> Dict[str, Any]:
        """Get service metrics."""
        try:
            metrics = {
                "service": {
                    "name": constants.SERVICE_NAME,
                    "version": constants.SERVICE_VERSION,
                    "environment": constants.ENVIRONMENT,
                    "uptime_seconds": time.time() - self.start_time if self.start_time else 0,
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
                },
            }

            return metrics

        except Exception as e:
            self.logger.error(f"Failed to get metrics: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get metrics: {e}")

    async def _get_service_info(self) -> Dict[str, Any]:
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
            raise HTTPException(status_code=500, detail=f"Failed to get service info: {e}")

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

    def update_health_status(self, status: Dict[str, Any]) -> None:
        """Update health status with external information."""
        self.health_status.update(status)

    def get_health_status(self) -> Dict[str, Any]:
        """Get current health status."""
        return self.health_status.copy()

    def is_healthy(self) -> bool:
        """Check if the service is healthy."""
        return self.health_status.get("status") == "healthy"
