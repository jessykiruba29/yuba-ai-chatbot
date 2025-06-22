from fastapi import FastAPI

app = FastAPI()
@app.get("/news")
def get_news():
    return {"headline": "AI is changing the world!"}

@app.get("/weather")
def get_weather():
    return {"forecast": "Rainy day with thunderstorms"}