"""
Minimal dev server — run this to test the geolocation module locally.

    python main.py

Then open:  http://127.0.0.1:8000/api/location
Test mode:  http://127.0.0.1:8000/api/location?ip=8.8.8.8
"""

from fastapi import FastAPI
from geolocation_service import router

app = FastAPI(title="Findy — Geolocation Dev Server")
app.include_router(router, prefix="/api")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
