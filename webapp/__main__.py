"""Run the local web app: ``python -m webapp`` (serves on http://localhost:8000)."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("webapp.app:app", host="127.0.0.1", port=8000)
