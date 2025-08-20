"""
Petrosa Realtime Strategies - Stateless Trading Signal Service

A high-performance, stateless trading signal service that processes real-time
market data from NATS and generates trading signals using multiple strategies.

This service is designed to be completely stateless, horizontally scalable,
and production-ready for enterprise deployment.
"""

__version__ = "1.0.0"
__author__ = "Petrosa Systems"
__email__ = "info@petrosa.com"

from .main import app

__all__ = ["app"]
