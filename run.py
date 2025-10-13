from fastapi import FastAPI, Request
from bot.events import handle_app_mention
from dotenv import load_dotenv
import logging
import os

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

app = FastAPI()

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
        if event.get('type') == 'app_mention':
            await handle_app_mention(event)
    
    return {"status": "ok"}

@app.get('/health')
def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "pqf-slack-bot"}

@app.post("/test_command")
async def test_command(command: str, channel: str = "", thread_ts: str = "", text: str = ""):
    """Test endpoint to call handle_command for debugging."""
    from bot.command import handle_command
    result = handle_command(command, channel, thread_ts, text=text)
    return {"result": result}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)