from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello World - Profeat PQF Slack Bot"}

@app.post("/slack/events")
async def slack_events():
    # Minimal event handler - replace with actual logic from apps.py
    return {"message": "Hello World - Profeat PQF Slack Bot from Slack Events"}

@app.get('/health')
def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "pqf-slack-bot"}