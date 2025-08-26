import os
import random
import time
from datetime import datetime, timezone
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse, Response
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="HRT SRE Portal",
    description="Demo portal application for SRE playground",
    version="1.0.0"
)

REQUEST_COUNT = Counter(
    'portal_requests_total', 
    'Total HTTP requests', 
    ['method', 'endpoint', 'status']
)

REQUEST_DURATION = Histogram(
    'portal_request_duration_seconds', 
    'HTTP request duration in seconds',
    ['method', 'endpoint']
)

ACTIVE_CONNECTIONS = Gauge(
    'portal_active_connections', 
    'Number of active connections'
)

ERROR_RATE = Gauge(
    'portal_error_rate', 
    'Current error rate percentage'
)

FAILURE_RATE = float(os.getenv('FAILURE_RATE', '0.0'))
startup_time = time.time()

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start_time = time.time()
    ACTIVE_CONNECTIONS.inc()
    
    try:
        response = await call_next(request)
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.url.path,
            status=response.status_code
        ).inc()
        
        duration = time.time() - start_time
        REQUEST_DURATION.labels(
            method=request.method,
            endpoint=request.url.path
        ).observe(duration)
        
        return response
    finally:
        ACTIVE_CONNECTIONS.dec()

@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <html>
        <head><title>HRT SRE Portal</title></head>
        <body>
            <h1>🚀 HRT SRE Portal</h1>
            <p>Welcome to the SRE playground portal!</p>
            <ul>
                <li><a href="/health">Health Check</a></li>
                <li><a href="/metrics">Metrics</a></li>
                <li><a href="/api/users">Users API</a></li>
                <li><a href="/api/orders">Orders API</a></li>
                <li><a href="/stress">Stress Test</a></li>
            </ul>
        </body>
    </html>
    """

@app.get("/health")
async def health():
    if random.random() < FAILURE_RATE:
        ERROR_RATE.set(FAILURE_RATE * 100)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    
    ERROR_RATE.set(0)
    uptime = time.time() - startup_time
    return {
        "status": "healthy",
        "uptime_seconds": round(uptime, 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "failure_rate": FAILURE_RATE
    }

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.get("/api/users")
async def get_users(limit: Optional[int] = 10):
    if random.random() < FAILURE_RATE:
        raise HTTPException(status_code=500, detail="Database connection failed")
    
    time.sleep(random.uniform(0.01, 0.1))
    
    users = []
    for i in range(min(limit, 100)):
        users.append({
            "id": i + 1,
            "name": f"user_{i+1}",
            "email": f"user{i+1}@example.com",
            "active": random.choice([True, False])
        })
    
    return {"users": users, "total": len(users)}

@app.get("/api/orders")
async def get_orders(user_id: Optional[int] = None):
    if random.random() < FAILURE_RATE:
        raise HTTPException(status_code=502, detail="Payment service unavailable")
    
    time.sleep(random.uniform(0.05, 0.3))
    
    orders = []
    order_count = random.randint(1, 20)
    
    for i in range(order_count):
        orders.append({
            "id": i + 1,
            "user_id": user_id or random.randint(1, 100),
            "amount": round(random.uniform(10.0, 1000.0), 2),
            "status": random.choice(["pending", "completed", "cancelled"]),
            "created_at": datetime.now(timezone.utc).isoformat()
        })
    
    return {"orders": orders, "total": len(orders)}

@app.get("/stress")
async def stress_test(duration: Optional[int] = 5):
    """Endpoint to generate load for testing"""
    if duration > 30:
        raise HTTPException(status_code=400, detail="Duration too long, max 30 seconds")
    
    start = time.time()
    operations = 0
    
    while time.time() - start < duration:
        _ = sum(range(1000))
        operations += 1
    
    actual_duration = time.time() - start
    
    return {
        "duration_requested": duration,
        "duration_actual": round(actual_duration, 2),
        "operations_completed": operations,
        "ops_per_second": round(operations / actual_duration, 2)
    }

@app.exception_handler(Exception)
async def exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}")
    ERROR_RATE.set(min(ERROR_RATE._value.get() + 5, 100))
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

if __name__ == "__main__":
    port = int(os.getenv('PORT', '8000'))
    uvicorn.run(app, host="0.0.0.0", port=port)