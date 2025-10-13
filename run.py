from fastapi import FastAPI, Request
from bot.events import handle_app_mention
from dotenv import load_dotenv
import logging
import os
from typing import Set
import time
import asyncio

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

app = FastAPI()

# In-memory cache for processed event IDs to prevent duplicate processing
_processed_events: Set[str] = set()
_CACHE_CLEANUP_INTERVAL = 3600  # Clean up old events every hour
_last_cleanup = time.time()

def _get_event_key(event: dict) -> str:
    """Generate a unique key for an event based on its content."""
    event_type = event.get('type', '')
    if event_type == 'app_mention':
        # Use combination of channel, ts, and text for uniqueness
        channel = event.get('channel', '')
        ts = event.get('ts', '')
        text = event.get('text', '')
        # Create a hash of the key components
        key = f"app_mention:{channel}:{ts}:{hash(text)}"
        return key
    return f"{event_type}:{event.get('event_id', event.get('id', ''))}"

def _is_event_already_processed(event: dict) -> bool:
    """Check if an event has already been processed based on content."""
    global _processed_events, _last_cleanup
    
    # Clean up old events periodically
    current_time = time.time()
    if current_time - _last_cleanup > _CACHE_CLEANUP_INTERVAL:
        # Clear old events (simple approach - clear all)
        _processed_events.clear()
        _last_cleanup = current_time
        logging.info("Cleaned up processed events cache")
    
    event_key = _get_event_key(event)
    if event_key in _processed_events:
        logging.info(f"Event {event_key} already processed, skipping")
        return True
    
    _processed_events.add(event_key)
    return False

@app.get("/")
async def root():
    return {"message": "Hello World - Profeat PQF Slack Bot"}

@app.post("/slack/events")
async def slack_events(request: Request):
    data = await request.json()
    
    # Handle URL verification challenge
    if data.get('type') == 'url_verification':
        return {"challenge": data.get('challenge')}
    
    # Handle app mention events
    if data.get('type') == 'event_callback':
        event = data.get('event', {})
        
        # Check for duplicate events based on content
        if _is_event_already_processed(event):
            return {"status": "duplicate event ignored"}
        
        if event.get('type') == 'app_mention':
            # Process in background using asyncio to return response immediately
            asyncio.create_task(handle_app_mention(event))
    
    # Always return success immediately to prevent Slack retries
    return {"status": "ok"}

@app.get('/health')
def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "pqf-slack-bot"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)