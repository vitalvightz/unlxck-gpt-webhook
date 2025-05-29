from fastapi import FastAPI, Request
import openai
import os

openai.api_key = os.getenv("OPENAI_API_KEY")
app = FastAPI()

@app.post("/webhook")
async def handle_submission(request: Request):
    data = await request.json()
    print("FULL PAYLOAD FROM TALLY:", data)  # <== This will show you the true structure

    return {"status": "received for debug"}
