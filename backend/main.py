from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import google.generativeai as genai
import httpx
import json
import logging
from typing import Optional
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import os
from datetime import datetime
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from fastapi import Request
from starlette.responses import Response


app = FastAPI()
@app.middleware("http")
async def custom_cors_middleware(request: Request, call_next):
    origin = request.headers.get("origin")
    if request.method == "OPTIONS":
        response = Response()
    else:
        response = await call_next(request)

    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type, Accept"
    
    return response
# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


load_dotenv()
genai_api_key = os.getenv("GENAI_API_KEY")
genai.configure(api_key=genai_api_key)
model = genai.GenerativeModel("gemini-1.5-flash")

# Pydantic Models
class ConfigURL(BaseModel):
    configuration: str
    userEmail: Optional[str] = None

class MessageData(BaseModel):
    config_url: ConfigURL
    message: str

class FormatReq(BaseModel):
    raw_data: dict | list | str
    org_msg: str


rag_cache = {}

async def prepare_rag_data(url: str):
    if url in rag_cache:
        return

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10)

        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        full_text = soup.get_text(separator=" ", strip=True)
        words = full_text.split()
        chunks = [' '.join(words[i:i + 50]) for i in range(0, len(words), 50)]

        tfidf = TfidfVectorizer().fit(chunks)
        vectors = tfidf.transform(chunks)

        rag_cache[url] = {
            "chunks": chunks,
            "tfidf": tfidf,
            "vectors": vectors
        }

    except Exception as e:
        logger.error(f"Failed to prepare RAG for {url}: {e}")
        rag_cache[url] = None

def retrieve_relevant_chunks(url: str, query: str, top_k: int = 3):
    data = rag_cache.get(url)
    if not data:
        return []

    query_vec = data["tfidf"].transform([query])
    scores = cosine_similarity(query_vec, data["vectors"]).flatten()
    top_indices = scores.argsort()[-top_k:][::-1]
    return [data["chunks"][i] for i in top_indices]

# Check if message is site-related
async def is_site_related(message: str) -> bool:
    prompt = f"""
You're a helper AI. The user typed: "{message}"
Does this message refer to information that would be on a company's website?
Reply only with "yes" or "no".
"""
    try:
        response = await model.generate_content_async(prompt)
        reply = response.text.strip().lower()
        return "yes" in reply
    except Exception as e:
        logger.warning(f"Site-related check failed: {e}")
        return False

# Gemini AI Handler
class GeminiAI:
    async def generate_content(self, prompt: str) -> str:
        try:
            response = await model.generate_content_async(prompt)
            json_text = response.text.strip()
            if json_text.startswith("```json"):
                json_text = json_text[7:]
            if json_text.endswith("```"):
                json_text = json_text[:-3]
            return json_text.strip()
        except Exception as e:
            logger.error(f"Gemini API error: {str(e)}")
            return json.dumps({"response": f"AI service error: {str(e)}"})

    async def extract_intent_and_payload(self, user_message: str, config_data: dict, email: str = None) -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        base_url = config_data.get("base_url", "")
        site_info = ""

        is_site_query = await is_site_related(user_message)
        if base_url and is_site_query:
            await prepare_rag_data(base_url)
            chunks = retrieve_relevant_chunks(base_url, user_message)
            site_info = "\n".join(chunks)
            logger.info(f"Retrieved {len(chunks)} relevant chunks from {base_url}")
            logger.info(f"chunks are: {chunks}")

        prompt = f"""
You are Yuba, which stands for Your Ultimate Backend Agent, a helpful and smart assistant.
if the user chats casually, you must also chat in a fun way. keep the convo short.

You help users interact with their website by calling the appropriate API endpoints.
If the user says 'today', 'tomorrow', or 'next Monday', convert to ISO date format.
Today is {today}.

If the user asks about the website or any info from it, answer from the below relevant content only:
{site_info if site_info else "(No content found)"}

Match user intent with endpoint and return JSON like:
{{
  "action": "<action from config>",
  "payload": {{ ... }}
}}

If no match, return a friendly message like:
{{ "response": "Sorry, I couldn't find anything related." }}

CONFIG:
{json.dumps(config_data.get("endpoints", []), indent=2)}

USER MESSAGE: "{user_message}"
USER EMAIL: "{email if email else 'Not provided'}"
"""
        return await self.generate_content(prompt)


class AIChatBot:
    def __init__(self):
        self.ai = GeminiAI()

    async def handle_message(self, message: str, config_url: str, email: str):
        try:
            async with httpx.AsyncClient() as client:
                config_response = await client.get(config_url)
                config_data = config_response.json()

            logger.info("Loaded config endpoints.")
            ai_response = await self.ai.extract_intent_and_payload(message, config_data, email)
            logger.info(f"Raw AI response: {ai_response}")

            try:
                response_data = json.loads(ai_response)
            except json.JSONDecodeError:
                return {"response": ai_response}

            if "response" in response_data:
                return {"response": response_data["response"]}

            matched_action = response_data.get("action")
            user_payload = response_data.get("payload", {})
            matched_endpoint = next((ep for ep in config_data.get("endpoints", []) if ep.get("action") == matched_action), None)

            if not matched_endpoint:
                return {"response": "Sorry, I couldn't match the action with any known endpoint."}

            return {
                "callback": {
                    "action": matched_action,
                    "payload": user_payload
                }
            }

        except Exception as e:
            logger.error(f"Error in handle_message: {str(e)}")
            return {"response": "Something went wrong while processing your request."}


chatbot = AIChatBot()

@app.post("/chat")
async def chat_with_bot(data: MessageData):
    logger.info(f"Received request from user: {data.message}")
    return await chatbot.handle_message(
        data.message,
        data.config_url.configuration,
        data.config_url.userEmail
    )

@app.post("/format")
async def format_response(data: FormatReq):
    prompt = f"""You're a helpful assistant. Don't say 'your' if data is shared or public.
User asked: "{data.org_msg}"
Backend returned: {data.raw_data}

Format this clearly using commas, DON'T use *, or emails in response.
"""
    response = model.generate_content(prompt)
    return {"response": response.text}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
