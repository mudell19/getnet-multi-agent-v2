from fastapi import FastAPI

from getnet_multi_agent.api import health

app = FastAPI(title="Getnet Multi-Agent Support")
app.include_router(health.router)
