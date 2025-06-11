from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import google.generativeai as genai
import httpx
import json
import logging
from typing import Optional
import re
from dotenv import load_dotenv
import os
from datetime import datetime
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup

app = FastAPI()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

load_dotenv()
genai_api_key = os.getenv("GENAI_API_KEY")
genai.configure(api_key=genai_api_key)
model = genai.GenerativeModel("gemini-1.5-flash")

class ConfigURL(BaseModel):
    configuration: str
    userEmail: Optional[str] = None


class MessageData(BaseModel):
    config_url: ConfigURL
    message: str

async def extract_text_from_url(url: str) -> str:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")

        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        return text[:4000]  # Limit for safety
    except Exception as e:
        return f"Unable to read site content: {e}"

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
        site_info = "" #empty initially

        base_url = config_data.get("base_url")
        if base_url:
            site_info = await extract_text_from_url(base_url)
        prompt = f"""
You are Yuba, a helpful and smart assistant.
if the user chats casually, you must also chat in a fun way.
keep the convo short.
You help users interact with their website by calling the appropriate API endpoints.
And if user says 'today' or 'tomorrow' or 'next monday', you have to correctly format the date in ISO FORMAT (yyyy-mm-dd).
use the reference for today , it is {today} , for tomorrow it is the day after {today}
Each endpoint has a description, action, method, and payload template.
{f"\nHere’s some content from the website:\n{site_info}" if site_info else ""}

Match the user's intent with the correct endpoint and return:
{{
  "action": "<action from config>",
  "payload": {{ ... }}
}}

✅ IMPORTANT:
If no endpoint matches, do NOT reply casually as plain text.
ALWAYS return your reply inside a JSON object like this:
{{
  "response": "friendly message here"
}}
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
            # Gemini just replied casually, not JSON
                return { "response": ai_response }

            if "response" in response_data:
                friendly = response_data["response"]
                base_url = config_data.get("base_url")
                if base_url:
                    page_summary = await extract_text_from_url(base_url)
                    friendly += f"\n\n🔍 I also found this info from the site:\n{page_summary}"
                return {"response": friendly}

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

class FormatReq(BaseModel):
    raw_data:dict | list | str
    org_msg:str

@app.post("/format")
async def format_response(data: FormatReq):
    prompt = f"""You're a helpful assistant.i can get info for something that i own or something that other people have shared. so DONT REPLY WITH 'your'.You are a smart chatbot. The user asked: "{data.org_msg}"
    and the backend gave this raw response {data.raw_data}. Please format it clearly using commas, and reply in a user friendly way with whatever you format(use comma "," dont use astericks "*" ) and dont show email in reply"
    """
    response =model.generate_content(prompt)
    return {"response": response.text}

