# Python standard

Use: 
- httpx
- rich
- click
- fastapi
- pyodmongo
- pydantic
- pydantic-settings
- aiogram
- pytest    


uv for package managment and running

# Testing

For local testing start the API on port 7000

Use playwright for testing the frontend in the browser.

Always run all local code with PARAMES_DEV_MODE=true

PARAMES_DEV_MODE=true uv run uvicorn parames.api:app --host 0.0.0.0 --port 7000