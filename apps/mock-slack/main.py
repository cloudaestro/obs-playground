import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any

import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, Response
from pydantic import BaseModel
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Mock Slack Webhook Receiver",
    description="Mock Slack service for testing alertmanager webhooks",
    version="1.0.0"
)

WEBHOOK_REQUESTS = Counter('mock_slack_webhook_requests_total', 'Total webhook requests', ['status'])
ALERTS_RECEIVED = Counter('mock_slack_alerts_received_total', 'Total alerts received', ['severity', 'alertname'])

alerts_history = []

class AlertmanagerWebhook(BaseModel):
    version: str
    groupKey: str
    truncatedAlerts: int = 0
    status: str
    receiver: str
    groupLabels: Dict[str, Any]
    commonLabels: Dict[str, Any]
    commonAnnotations: Dict[str, Any]
    externalURL: str
    alerts: list

@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <html>
        <head>
            <title>Mock Slack Webhook Receiver</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; }
                .alert { border: 1px solid #ddd; margin: 10px 0; padding: 10px; border-radius: 5px; }
                .firing { background-color: #ffebee; border-color: #f44336; }
                .resolved { background-color: #e8f5e8; border-color: #4caf50; }
                .timestamp { color: #666; font-size: 0.9em; }
                h1 { color: #333; }
                .count { background: #f0f0f0; padding: 5px 10px; border-radius: 3px; }
            </style>
        </head>
        <body>
            <h1>🔔 Mock Slack Webhook Receiver</h1>
            <p>Received <span class="count">{alert_count}</span> alerts</p>
            <div>
                <a href="/alerts">View All Alerts</a> | 
                <a href="/metrics">Metrics</a> | 
                <a href="/health">Health</a>
            </div>
            <h2>Recent Alerts</h2>
            <div id="alerts">
                {recent_alerts}
            </div>
        </body>
    </html>
    """.format(
        alert_count=len(alerts_history),
        recent_alerts=_format_recent_alerts()
    )

def _format_recent_alerts():
    """Format recent alerts for HTML display"""
    if not alerts_history:
        return "<p>No alerts received yet.</p>"
    
    html = ""
    for alert in alerts_history[-10:]:
        css_class = "firing" if alert['status'] == 'firing' else "resolved"
        html += f"""
        <div class="alert {css_class}">
            <strong>{alert['alertname']}</strong> - {alert['status'].upper()}
            <div class="timestamp">{alert['timestamp']}</div>
            <div>{alert['summary']}</div>
        </div>
        """
    
    return html

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "mock-slack",
        "alerts_received": len(alerts_history),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.get("/alerts")
async def get_alerts():
    """Get all received alerts"""
    return {
        "alerts": alerts_history,
        "total": len(alerts_history),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.post("/webhook")
async def webhook(request: Request):
    """Main webhook endpoint for receiving Alertmanager notifications"""
    try:
        payload = await request.json()
        logger.info(f"Received webhook payload: {json.dumps(payload, indent=2)}")
        
        webhook_data = AlertmanagerWebhook(**payload)
        
        for alert in webhook_data.alerts:
            alert_info = {
                "alertname": alert.get("labels", {}).get("alertname", "unknown"),
                "instance": alert.get("labels", {}).get("instance", "unknown"),
                "severity": alert.get("labels", {}).get("severity", "unknown"),
                "status": alert.get("status", "unknown"),
                "summary": alert.get("annotations", {}).get("summary", "No summary available"),
                "description": alert.get("annotations", {}).get("description", ""),
                "starts_at": alert.get("startsAt", ""),
                "ends_at": alert.get("endsAt", ""),
                "generator_url": alert.get("generatorURL", ""),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "raw_alert": alert
            }
            
            alerts_history.append(alert_info)
            
            ALERTS_RECEIVED.labels(
                severity=alert_info["severity"],
                alertname=alert_info["alertname"]
            ).inc()
            
            logger.info(
                f"Alert received: {alert_info['alertname']} "
                f"({alert_info['severity']}) - {alert_info['status']}"
            )
        
        WEBHOOK_REQUESTS.labels(status='success').inc()
        
        response = {
            "status": "success",
            "message": f"Processed {len(webhook_data.alerts)} alerts",
            "receiver": webhook_data.receiver,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        logger.info(f"Webhook processed successfully: {response}")
        return JSONResponse(content=response, status_code=200)
    
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        WEBHOOK_REQUESTS.labels(status='error').inc()
        
        error_response = {
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        return JSONResponse(content=error_response, status_code=500)

@app.post("/slack/webhook")
async def slack_webhook(request: Request):
    """Alternative endpoint that mimics Slack webhook format"""
    try:
        payload = await request.json()
        logger.info(f"Received Slack-format webhook: {json.dumps(payload, indent=2)}")
        
        alert_info = {
            "alertname": "slack-formatted",
            "instance": "unknown",
            "severity": "info",
            "status": "notification",
            "summary": payload.get("text", "Slack notification received"),
            "description": payload.get("text", ""),
            "channel": payload.get("channel", "#alerts"),
            "username": payload.get("username", "alertmanager"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "raw_payload": payload
        }
        
        alerts_history.append(alert_info)
        WEBHOOK_REQUESTS.labels(status='success').inc()
        ALERTS_RECEIVED.labels(severity='info', alertname='slack-formatted').inc()
        
        return {"ok": True}
    
    except Exception as e:
        logger.error(f"Error processing Slack webhook: {e}")
        WEBHOOK_REQUESTS.labels(status='error').inc()
        return JSONResponse(content={"ok": False, "error": str(e)}, status_code=500)

@app.delete("/alerts")
async def clear_alerts():
    """Clear all alerts (useful for testing)"""
    global alerts_history
    count = len(alerts_history)
    alerts_history = []
    
    logger.info(f"Cleared {count} alerts")
    
    return {
        "status": "success",
        "message": f"Cleared {count} alerts",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/stats")
async def get_stats():
    """Get statistics about received alerts"""
    if not alerts_history:
        return {
            "total_alerts": 0,
            "by_status": {},
            "by_severity": {},
            "by_alertname": {}
        }
    
    stats = {
        "total_alerts": len(alerts_history),
        "by_status": {},
        "by_severity": {},
        "by_alertname": {}
    }
    
    for alert in alerts_history:
        status = alert.get("status", "unknown")
        severity = alert.get("severity", "unknown")
        alertname = alert.get("alertname", "unknown")
        
        stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
        stats["by_severity"][severity] = stats["by_severity"].get(severity, 0) + 1
        stats["by_alertname"][alertname] = stats["by_alertname"].get(alertname, 0) + 1
    
    return stats

if __name__ == "__main__":
    port = int(os.getenv('PORT', '8080'))
    uvicorn.run(app, host="0.0.0.0", port=port)