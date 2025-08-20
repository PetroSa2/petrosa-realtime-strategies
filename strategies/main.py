#!/usr/bin/env python3
"""
Main entry point for the Petrosa Realtime Strategies service.

This module handles the startup, configuration, and graceful shutdown
of the trading signal service.
"""

import asyncio
import os
import signal
import sys
from typing import Optional

import typer
from dotenv import load_dotenv

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

import constants  # noqa: E402
from strategies.core.consumer import NATSConsumer  # noqa: E402
from strategies.core.publisher import TradeOrderPublisher  # noqa: E402
from strategies.health.server import HealthServer  # noqa: E402
from strategies.utils.logger import setup_logging  # noqa: E402

# Initialize OpenTelemetry as early as possible
try:
    from otel_init import setup_telemetry, setup_metrics  # noqa: E402

    if not os.getenv("OTEL_NO_AUTO_INIT"):
        setup_telemetry(service_name=constants.OTEL_SERVICE_NAME)
        setup_metrics()
except ImportError:
    pass

# Load environment variables
load_dotenv()

app = typer.Typer(help="Petrosa Realtime Strategies - Trading Signal Service")


class StrategiesService:
    """Main service class for the Realtime Strategies service."""

    def __init__(self):
        """Initialize the service."""
        self.logger = setup_logging(level=constants.LOG_LEVEL)
        self.consumer: Optional[NATSConsumer] = None
        self.publisher: Optional[TradeOrderPublisher] = None
        self.health_server: Optional[HealthServer] = None
        self.shutdown_event = asyncio.Event()

    async def start(self):
        """Start the service."""
        self.logger.info("Starting Petrosa Realtime Strategies service")

        try:
            # Start health server
            self.health_server = HealthServer(
                port=constants.HEALTH_CHECK_PORT, logger=self.logger
            )
            await self.health_server.start()
            self.logger.info(
                f"Health server started on port {constants.HEALTH_CHECK_PORT}"
            )

            # Start trade order publisher
            self.publisher = TradeOrderPublisher(
                nats_url=constants.NATS_URL,
                topic=constants.NATS_PUBLISHER_TOPIC,
                logger=self.logger,
            )
            await self.publisher.start()
            self.logger.info("Trade order publisher started successfully")

            # Start NATS consumer
            self.consumer = NATSConsumer(
                nats_url=constants.NATS_URL,
                topic=constants.NATS_CONSUMER_TOPIC,
                consumer_name=constants.NATS_CONSUMER_NAME,
                consumer_group=constants.NATS_CONSUMER_GROUP,
                publisher=self.publisher,
                logger=self.logger,
            )
            await self.consumer.start()
            self.logger.info("NATS consumer started successfully")

            # Wait for shutdown signal
            await self.shutdown_event.wait()

        except Exception as e:
            self.logger.error(f"Error starting service: {e}")
            raise
        finally:
            await self.stop()

    async def stop(self):
        """Stop the service gracefully."""
        self.logger.info("Stopping Petrosa Realtime Strategies service")

        # Stop NATS consumer
        if self.consumer:
            await self.consumer.stop()
            self.logger.info("NATS consumer stopped")

        # Stop trade order publisher
        if self.publisher:
            await self.publisher.stop()
            self.logger.info("Trade order publisher stopped")

        # Stop health server
        if self.health_server:
            await self.health_server.stop()
            self.logger.info("Health server stopped")

        self.logger.info("Service stopped gracefully")


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    print(f"\nReceived signal {signum}, shutting down gracefully...")
    if hasattr(signal_handler, "service"):
        asyncio.create_task(signal_handler.service.shutdown_event.set())


@app.command()
def run(
    nats_url: Optional[str] = typer.Option(
        None, "--nats-url", help="NATS server URL"
    ),
    consumer_topic: Optional[str] = typer.Option(
        None, "--consumer-topic", help="NATS consumer topic"
    ),
    publisher_topic: Optional[str] = typer.Option(
        None, "--publisher-topic", help="NATS publisher topic"
    ),
    log_level: str = typer.Option(
        constants.LOG_LEVEL, "--log-level", help="Logging level"
    ),
):
    """Run the Realtime Strategies service."""
    # Override constants with command line arguments
    if nats_url:
        os.environ["NATS_URL"] = nats_url
    if consumer_topic:
        os.environ["NATS_CONSUMER_TOPIC"] = consumer_topic
    if publisher_topic:
        os.environ["NATS_PUBLISHER_TOPIC"] = publisher_topic
    if log_level:
        os.environ["LOG_LEVEL"] = log_level

    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Create and run service
    service = StrategiesService()
    signal_handler.service = service

    try:
        asyncio.run(service.start())
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
    except Exception as e:
        print(f"Service failed: {e}")
        sys.exit(1)


@app.command()
def health():
    """Check service health."""
    import requests

    try:
        response = requests.get(
            f"http://localhost:{constants.HEALTH_CHECK_PORT}/healthz", timeout=5
        )
        if response.status_code == 200:
            print("✅ Service is healthy")
            print(f"Response: {response.json()}")
        else:
            print(f"❌ Service is unhealthy: {response.status_code}")
            sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"❌ Health check failed: {e}")
        sys.exit(1)


@app.command()
def version():
    """Show version information."""
    from strategies import __version__

    print(f"Petrosa Realtime Strategies v{__version__}")


@app.command()
def config():
    """Show current configuration."""
    print("🔧 Current Configuration:")
    print(f"  Service Name: {constants.SERVICE_NAME}")
    print(f"  Version: {constants.SERVICE_VERSION}")
    print(f"  Environment: {constants.ENVIRONMENT}")
    print(f"  Log Level: {constants.LOG_LEVEL}")
    print(f"  NATS URL: {constants.NATS_URL}")
    print(f"  Consumer Topic: {constants.NATS_CONSUMER_TOPIC}")
    print(f"  Publisher Topic: {constants.NATS_PUBLISHER_TOPIC}")
    print(f"  Health Check Port: {constants.HEALTH_CHECK_PORT}")
    print(f"  Enabled Strategies: {constants.get_enabled_strategies()}")
    print(f"  Trading Symbols: {constants.TRADING_SYMBOLS}")
    print(f"  Enable Shorts: {constants.TRADING_ENABLE_SHORTS}")


if __name__ == "__main__":
    app()
