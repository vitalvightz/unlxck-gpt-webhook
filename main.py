from fastapi import FastAPI, Request

app = FastAPI()

@app.post("/webhook")
async def handle_submission(request: Request):
    data = await request.json()
    print("DEBUG: Full payload →", data)  # This shows what Tally is sending
    return {"status": "received"}
