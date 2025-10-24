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
from strategies.utils.heartbeat import HeartbeatManager  # noqa: E402

# Initialize OpenTelemetry as early as possible
try:
    import otel_init  # noqa: E402

    if not os.getenv("OTEL_NO_AUTO_INIT"):
        otel_init.setup_telemetry(service_name=constants.OTEL_SERVICE_NAME)
        otel_init.setup_metrics()
        # Note: Handler attachment moved to __init__ after setup_logging()
        # Health server will attach its own handler via lifespan
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
        
        # Attach OTLP logging handler AFTER setup_logging() configures logging
        # This ensures the handler survives any logging reconfiguration
        try:
            import otel_init
            otel_init.attach_logging_handler_simple()
        except Exception as e:
            print(f"⚠️  Failed to attach OTLP handler: {e}")
        
        self.consumer: Optional[NATSConsumer] = None
        self.publisher: Optional[TradeOrderPublisher] = None
        self.health_server: Optional[HealthServer] = None
        self.heartbeat_manager: Optional[HeartbeatManager] = None
        self.config_manager = None
        self.depth_analyzer = None
        self.shutdown_event = asyncio.Event()

    async def start(self):
        """Start the service."""
        self.logger.info(
            "Starting Petrosa Realtime Strategies service",
            event="service_starting",
            service_name=constants.SERVICE_NAME,
            service_version=constants.SERVICE_VERSION,
            environment=constants.ENVIRONMENT
        )

        try:
            # Initialize MongoDB and Configuration Manager FIRST
            from strategies.db.mongodb_client import MongoDBClient
            from strategies.services.config_manager import StrategyConfigManager
            from strategies.services.depth_analyzer import DepthAnalyzer
            
            mongodb_client = MongoDBClient(
                uri=constants.MONGODB_URI,
                database=constants.MONGODB_DATABASE,
                timeout_ms=constants.MONGODB_TIMEOUT_MS,
            )
            
            self.config_manager = StrategyConfigManager(
                mongodb_client=mongodb_client,
                cache_ttl_seconds=60,
            )
            await self.config_manager.start()
            self.logger.info(
                "Configuration manager initialized",
                event="config_manager_initialized",
                cache_ttl_seconds=60
            )
            
            # Initialize depth analyzer for market metrics
            self.depth_analyzer = DepthAnalyzer(
                history_window_seconds=900,  # 15 minutes
                max_symbols=100,
                metrics_ttl_seconds=300,  # 5 minutes
            )
            self.logger.info(
                "Depth analyzer initialized",
                event="depth_analyzer_initialized",
                history_window_seconds=900,
                max_symbols=100,
                metrics_ttl_seconds=300
            )
            
            # Start health server first to handle Kubernetes probes
            self.health_server = HealthServer(
                port=constants.HEALTH_CHECK_PORT,
                logger=self.logger,
                consumer=None,  # Will be set later
                publisher=None,  # Will be set later
                heartbeat_manager=None,  # Will be set later
                config_manager=self.config_manager,  # NEW
                depth_analyzer=self.depth_analyzer,  # NEW
            )
            await self.health_server.start()
            self.logger.info(
                "Health server started",
                event="health_server_started",
                port=constants.HEALTH_CHECK_PORT
            )

            # Start trade order publisher
            self.publisher = TradeOrderPublisher(
                nats_url=constants.NATS_URL,
                topic=constants.NATS_PUBLISHER_TOPIC,
                logger=self.logger,
            )
            await self.publisher.start()

            # Update health server with publisher reference
            self.health_server.publisher = self.publisher

            # Start NATS consumer
            self.consumer = NATSConsumer(
                nats_url=constants.NATS_URL,
                topic=constants.NATS_CONSUMER_TOPIC,
                consumer_name=constants.NATS_CONSUMER_NAME,
                consumer_group=constants.NATS_CONSUMER_GROUP,
                publisher=self.publisher,
                logger=self.logger,
                depth_analyzer=self.depth_analyzer,  # NEW
            )
            await self.consumer.start()
            self.logger.info(
                "NATS consumer started",
                event="nats_consumer_started",
                topic=constants.NATS_CONSUMER_TOPIC
            )

            # Update health server with consumer reference
            self.health_server.consumer = self.consumer

            # Start heartbeat manager
            self.heartbeat_manager = HeartbeatManager(
                consumer=self.consumer,
                publisher=self.publisher,
                logger=self.logger,
            )
            await self.heartbeat_manager.start()
            self.logger.info(
                "Heartbeat manager started",
                event="heartbeat_manager_started",
                interval_seconds=constants.HEARTBEAT_INTERVAL_SECONDS
            )

            # Update health server with heartbeat manager reference
            self.health_server.heartbeat_manager = self.heartbeat_manager

            # Wait for shutdown signal
            await self.shutdown_event.wait()

        except Exception as e:
            self.logger.error("Error starting service", event_type="service_start_error", error=str(e))
            raise
        finally:
            await self.stop()

    async def stop(self):
        """Stop the service gracefully."""
        self.logger.info("Stopping Petrosa Realtime Strategies service", event_type="service_stopping")

        # Stop heartbeat manager first
        if self.heartbeat_manager:
            await self.heartbeat_manager.stop()
            self.logger.info("Heartbeat manager stopped", event_type="heartbeat_manager_stopped")

        # Stop NATS consumer
        if self.consumer:
            await self.consumer.stop()
            self.logger.info("NATS consumer stopped", event_type="nats_consumer_stopped")

        # Stop trade order publisher
        if self.publisher:
            await self.publisher.stop()
            self.logger.info("Trade order publisher stopped", event_type="publisher_stopped")

        # Stop health server
        if self.health_server:
            await self.health_server.stop()
            self.logger.info("Health server stopped", event_type="health_server_stopped")
        
        # Stop configuration manager
        if self.config_manager:
            await self.config_manager.stop()
            self.logger.info("Configuration manager stopped", event_type="config_manager_stopped")

        self.logger.info("Service stopped gracefully", event_type="service_stopped")


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
    print(f"  Heartbeat Enabled: {constants.HEARTBEAT_ENABLED}")
    print(f"  Heartbeat Interval: {constants.HEARTBEAT_INTERVAL_SECONDS}s")
    print(f"  Enabled Strategies: {constants.get_enabled_strategies()}")
    print(f"  Trading Symbols: {constants.TRADING_SYMBOLS}")
    print(f"  Enable Shorts: {constants.TRADING_ENABLE_SHORTS}")


@app.command()
def heartbeat():
    """Trigger a manual heartbeat (for testing)."""
    import requests
    
    try:
        # Try to trigger heartbeat via health endpoint
        response = requests.get(
            f"http://localhost:{constants.HEALTH_CHECK_PORT}/metrics", timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            heartbeat_info = data.get("components", {}).get("heartbeat", {})
            print("💓 Heartbeat Status:")
            print(f"  Enabled: {heartbeat_info.get('enabled', 'unknown')}")
            print(f"  Running: {heartbeat_info.get('is_running', 'unknown')}")
            print(f"  Count: {heartbeat_info.get('heartbeat_count', 'unknown')}")
            print(f"  Uptime: {heartbeat_info.get('uptime_seconds', 'unknown')}s")
            print(f"  Interval: {heartbeat_info.get('interval_seconds', 'unknown')}s")
            
            # Show recent stats if available
            consumer_info = data.get("components", {}).get("consumer", {})
            publisher_info = data.get("components", {}).get("publisher", {})
            print("\n📊 Current Stats:")
            print(f"  Messages Processed: {consumer_info.get('message_count', 'unknown')}")
            print(f"  Consumer Errors: {consumer_info.get('error_count', 'unknown')}")
            print(f"  Orders Published: {publisher_info.get('order_count', 'unknown')}")
            print(f"  Publisher Errors: {publisher_info.get('error_count', 'unknown')}")
        else:
            print(f"❌ Failed to get heartbeat status: {response.status_code}")
            sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"❌ Heartbeat check failed: {e}")
        print("💡 Make sure the service is running")
        sys.exit(1)


if __name__ == "__main__":
    app()
