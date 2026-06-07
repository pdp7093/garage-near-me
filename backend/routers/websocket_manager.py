"""
GarageNearMe — WebSocket Manager
Mechanic + Customer dono ke connections track karta hai.
WebRTC signaling relay bhi karta hai.
"""
from fastapi import WebSocket
from typing import Dict, Set
import logging

logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self):
        # garage_id → set of WebSocket connections
        self.mechanic_connections: Dict[int, Set[WebSocket]] = {}
        # customer_id → set of WebSocket connections
        self.customer_connections: Dict[int, Set[WebSocket]] = {}

    # ── Mechanic ──────────────────────────────────────────────────────────
    async def connect(self, garage_id: int, ws: WebSocket):
        await ws.accept()
        if garage_id not in self.mechanic_connections:
            self.mechanic_connections[garage_id] = set()
        self.mechanic_connections[garage_id].add(ws)
        logger.info(f"Mechanic WS connected — garage_id={garage_id}")

    def disconnect(self, garage_id: int, ws: WebSocket):
        if garage_id in self.mechanic_connections:
            self.mechanic_connections[garage_id].discard(ws)
            if not self.mechanic_connections[garage_id]:
                del self.mechanic_connections[garage_id]

    def is_online(self, garage_id: int) -> bool:
        return garage_id in self.mechanic_connections and bool(self.mechanic_connections[garage_id])

    async def send_to_garage(self, garage_id: int, data: dict):
        if garage_id not in self.mechanic_connections:
            return
        dead = set()
        for ws in self.mechanic_connections[garage_id]:
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.mechanic_connections[garage_id].discard(ws)
        if garage_id in self.mechanic_connections and not self.mechanic_connections[garage_id]:
            del self.mechanic_connections[garage_id]

    async def broadcast_to_garages(self, garage_ids: list, data: dict):
        sent_to = 0
        for garage_id in garage_ids:
            if self.is_online(garage_id):
                await self.send_to_garage(garage_id, data)
                sent_to += 1
        logger.info(f"WS broadcast → {sent_to}/{len(garage_ids)} online garages")
        return sent_to

    # ── Customer ──────────────────────────────────────────────────────────
    async def connect_customer(self, customer_id: int, ws: WebSocket):
        await ws.accept()
        if customer_id not in self.customer_connections:
            self.customer_connections[customer_id] = set()
        self.customer_connections[customer_id].add(ws)
        logger.info(f"Customer WS connected — customer_id={customer_id}")

    def disconnect_customer(self, customer_id: int, ws: WebSocket):
        if customer_id in self.customer_connections:
            self.customer_connections[customer_id].discard(ws)
            if not self.customer_connections[customer_id]:
                del self.customer_connections[customer_id]

    async def send_to_customer(self, customer_id: int, data: dict):
        if customer_id not in self.customer_connections:
            return
        dead = set()
        for ws in self.customer_connections[customer_id]:
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.customer_connections[customer_id].discard(ws)
        if customer_id in self.customer_connections and not self.customer_connections[customer_id]:
            del self.customer_connections[customer_id]

    def online_count(self) -> int:
        return len(self.mechanic_connections) + len(self.customer_connections)


# Singleton
ws_manager = WebSocketManager()