from fastapi import FastAPI

# Create the FastAPI app instance
analytics_api = FastAPI()

@analytics_api.get("/test")
async def test_endpoint():
    return {"message": "FastAPI is working!"}