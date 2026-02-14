from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import PyPDF2
import io
import os
import random
from datetime import datetime
from typing import List, Dict, Optional, AsyncGenerator
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs # type: ignore
from elevenlabs.play import play
import re
import json
import asyncio
import base64
from io import BytesIO
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import websockets
import httpx

from fastapi import WebSocket, WebSocketDisconnect
import websockets
import json
import base64

load_dotenv()
app = FastAPI()

# ----------------------------
# CORS (dev: allow all)
# ----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # dev only; lock down in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------
# In-memory storage (dev only)
# ----------------------------
conversations: Dict[str, Dict] = {}

# ----------------------------
# Pydantic models
# ----------------------------
class ChatMessage(BaseModel):
    conversation_id: str
    message: str

class StartChatRequest(BaseModel):
    conversation_id: str

class TTSRequest(BaseModel):
    text: str
    model_id: Optional[str] = "eleven_multilingual_v2"


# ----------------------------
# Helpers
# ----------------------------
def generate_question(resume_text: str, conversation_history: List[Dict]) -> str:
    questions = [
        "Tell me about your most recent work experience and key accomplishments.",
        "What programming languages or technologies are you most comfortable with?",
        "Describe a challenging project you worked on and how you overcame obstacles.",
        "What interests you most about this type of role?",
        "How do you stay updated with new technologies in your field?",
        "Tell me about a time you had to learn something completely new for a project.",
        "What are your career goals for the next few years?",
        "Describe your experience working in a team environment.",
        "What's a project you're particularly proud of?",
        "How do you approach problem-solving when faced with technical challenges?",
        "Tell me about your leadership experience.",
        "What motivates you in your work?",
        "How do you handle tight deadlines and pressure?",
        "Describe a time you disagreed with a team member. How did you handle it?",
        "What's the most innovative solution you've implemented?",
    ]

    asked_questions = [
        msg["content"]
        for msg in conversation_history
        if msg.get("type") == "ai_question" and "content" in msg
    ]

    available_questions = [q for q in questions if q not in asked_questions]
    if not available_questions:
        return "Thank you for sharing! Do you have any questions about the role or our company?"

    return random.choice(available_questions)


def generate_response(user_message: str) -> str:
    responses = [
        "That's great! Thanks for sharing that insight.",
        "Interesting! I can see how that experience would be valuable.",
        "Thanks for elaborating on that. That's really helpful context.",
        "I appreciate you walking me through that experience.",
        "That sounds like valuable experience. Thanks for the details.",
        "Great example! That shows strong problem-solving skills.",
        "That's impressive! It's clear you have solid experience in this area.",
        "Thanks for the detailed response. That gives me good insight into your background.",
        "Excellent! That demonstrates good technical knowledge.",
        "I can tell you've put thought into your career development.",
    ]
    return random.choice(responses)


def get_elevenlabs_config() -> tuple[str, str]:
    """
    Read env vars safely and return (api_key, voice_id).
    Raise a clean HTTP 500 if missing.
    make sure to load env at begining
    """
    api_key = os.getenv("ELEVENLABS_API_KEY")
    elevenlabs = ElevenLabs(
        api_key= api_key,
    )
    print(f"api_key: {api_key}")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID")
    print(f"voice id: {voice_id}")
    if not api_key or not voice_id:
        raise HTTPException(
            status_code=500,
            detail="Missing ELEVENLABS_API_KEY or ELEVENLABS_VOICE_ID in environment.",
        )
    return api_key, voice_id


# ----------------------------
# Routes
# ----------------------------
@app.get("/")
async def root():
    return {"message": "PDF Upload API is running!"}


@app.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    """
    Upload and extract text from PDF.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Empty file uploaded")

        pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))

        extracted_text_parts: List[str] = []
        for page in pdf_reader.pages:
            page_text = page.extract_text() or ""  # extract_text() can return None
            extracted_text_parts.append(page_text)

        extracted_text = "\n".join(extracted_text_parts).strip()

        if not extracted_text:
            raise HTTPException(
                status_code=400,
                detail="Could not extract text from PDF (it may be scanned/image-based).",
            )

        conversation_id = f"conv_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{random.randint(1000, 9999)}"
        conversations[conversation_id] = {
            "resume_text": extracted_text,
            "messages": [],
            "created_at": datetime.now().isoformat(),
        }

        return {
            "success": True,
            "message": "PDF processed successfully!",
            "filename": file.filename,
            "text_length": len(extracted_text),
            "text_preview": extracted_text[:500],
            "conversation_id": conversation_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")
# Optional: for voice WebSocket
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "")

# Gemini for AI Interviewer
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash-latest")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/start-chat")
async def start_chat(request: StartChatRequest):
    if request.conversation_id not in conversations:
        raise HTTPException(status_code=400, detail="Conversation not found")

    convo = conversations[request.conversation_id]
    first_question = generate_question(convo["resume_text"], convo["messages"])

    convo["messages"].append(
        {"type": "ai_question", "content": first_question, "timestamp": datetime.now().isoformat()}
    )

    return {"success": True, "question": first_question, "conversation_id": request.conversation_id}


@app.post("/send-message")
async def send_message(chat_data: ChatMessage):
    if chat_data.conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")

    convo = conversations[chat_data.conversation_id]

    convo["messages"].append(
        {"type": "user_response", "content": chat_data.message, "timestamp": datetime.now().isoformat()}
    )

    ai_response = generate_response(chat_data.message)
    convo["messages"].append(
        {"type": "ai_response", "content": ai_response, "timestamp": datetime.now().isoformat()}
    )

    next_question = generate_question(convo["resume_text"], convo["messages"])
    if next_question:
        convo["messages"].append(
            {"type": "ai_question", "content": next_question, "timestamp": datetime.now().isoformat()}
        )

    return {
        "success": True,
        "ai_response": ai_response,
        "next_question": next_question,
        "conversation_id": chat_data.conversation_id,
    }


@app.get("/conversation/{conversation_id}")
async def get_conversation(conversation_id: str):
    if conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"success": True, "conversation": conversations[conversation_id]}


@app.post("/api/tts")
async def tts(req: TTSRequest):
    """
    ElevenLabs TTS proxy. Returns audio/mpeg so the browser can play it.
    """
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")

    api_key, voice_id = get_elevenlabs_config()
    tts_url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"

    headers = {
        "xi-api-key": api_key,
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
    }
    payload = {"text": text, "model_id": req.model_id}

    async def audio_stream() -> AsyncGenerator[bytes, None]:
        timeout = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", tts_url, headers=headers, json=payload) as r:
                if r.status_code != 200:
                    err = await r.aread()
                    raise HTTPException(
                        status_code=502,
                        detail=f"ElevenLabs TTS error {r.status_code}: {err[:300].decode(errors='ignore')}",
                    )
                async for chunk in r.aiter_bytes():
                    if chunk:
                        yield chunk

    return StreamingResponse(audio_stream(), media_type="audio/mpeg")

from fastapi import WebSocket, WebSocketDisconnect
import asyncio
import json
import base64
import websockets

@app.websocket("/ws/stt")
async def ws_stt(ws: WebSocket):

# ----- Gemini: resume analysis and interview -----
def _strip_json(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```json?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def analyze_with_gemini(file_bytes: bytes, mime_type: str, job_title: str, job_description: str) -> dict:
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(GEMINI_MODEL)

    prompt = f"""You are an interviewer. Use the attached resume and this job info only to prepare for the interview. Do NOT score or evaluate the candidate yet — that happens after the interview based on their answers.

- Job title: {job_title}
- Job description: {job_description}

Respond with ONLY valid JSON (no markdown, no extra text) in this exact shape:
{{
  "resumeSummary": "2-3 sentence summary of the candidate from the resume (for interview context only)",
  "firstQuestion": "the first interview question to ask this candidate for this role (one question only)"
}}"""

    if mime_type == "application/pdf":
        buf = BytesIO(file_bytes)
        uploaded = genai.upload_file(path=buf, mime_type="application/pdf", display_name="resume.pdf")
        response = model.generate_content([uploaded, prompt])
    else:
        text = file_bytes.decode("utf-8", errors="replace")
        response = model.generate_content(f"Resume content:\n{text}\n\n{prompt}")

    if not response or not response.text:
        raise ValueError("Gemini returned no text (possible safety block or error)")
    raw = response.text.strip()
    json_str = _strip_json(raw)
    out = json.loads(json_str)
    if "firstQuestion" not in out or "resumeSummary" not in out:
        raise ValueError("Invalid shape from Gemini (missing firstQuestion or resumeSummary)")
    return out


def get_next_question(resume_summary: str, job_title: str, job_description: str, messages: list) -> dict:
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(GEMINI_MODEL)

    convo = "\n".join(
        f"Interviewer: {m['content']}" if m["role"] == "assistant" else f"Candidate: {m['content']}"
        for m in messages
    )
    prompt = f"""You are an interviewer. Your job is to ask questions that COVER DIFFERENT AREAS from the resume and job description (experience, projects, skills, motivation, role-fit). Do NOT drill into one topic with follow-ups — move to a NEW area for each question. Ask 5-7 questions total.

Candidate resume summary: {resume_summary}
Job title: {job_title}
Job description: {job_description}

Conversation so far:
{convo}

The candidate just gave their last answer. Respond with ONLY valid JSON (no markdown).

If you have more topics to cover:
{{
  "nextQuestion": "<your next question — on a DIFFERENT topic/area from resume or job>"
}}

When you have asked enough questions (5-7 total), end the interview and evaluate how well they answered based on their resume and the job description:
{{
  "done": true,
  "overallScore": <number 0-100: how well they answered the questions given their background and the role — consider relevance, depth, clarity, and fit>,
  "overallFeedback": "<2-4 sentences summarizing how well they did: what was strong, what could improve, and how their answers aligned with the job. Base this only on their interview answers and the resume/job.>",
  "closingMessage": "<brief closing, e.g. Thank you for your time. We'll be in touch.>"
}}"""
    response = model.generate_content(prompt)
    if not response or not response.text:
        raise ValueError("No response from Gemini")
    raw = response.text.strip()
    json_str = _strip_json(raw)
    return json.loads(json_str)


@app.get("/api/health")
def api_health():
    return {"ok": True}


@app.post("/api/analyze")
async def api_analyze(
    resume: UploadFile = File(...),
    jobTitle: str = Form(""),
    jobDescription: str = Form(""),
):
    if not GEMINI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Gemini API key not set. Add GEMINI_API_KEY to backend/.env (see .env.example).",
        )
    if not resume.filename:
        raise HTTPException(status_code=400, detail="Resume file is required")
    try:
        file_bytes = await resume.read()
        mime = resume.content_type or "application/octet-stream"
        if "pdf" in mime or (resume.filename and resume.filename.lower().endswith(".pdf")):
            mime = "application/pdf"
        analysis = analyze_with_gemini(file_bytes, mime, jobTitle, jobDescription)
        return analysis
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail="Gemini returned invalid JSON. Try again or use a different resume.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/interview/next")
async def api_interview_next(body: dict):
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=503, detail="Gemini API key not set.")
    resume_summary = body.get("resumeSummary")
    messages = body.get("messages", [])
    if not resume_summary or not isinstance(messages, list) or len(messages) == 0:
        raise HTTPException(status_code=400, detail="resumeSummary and messages array required")
    try:
        out = get_next_question(
            resume_summary,
            body.get("jobTitle", ""),
            body.get("jobDescription", ""),
            messages,
        )
        return out
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws/voice")
async def ws_voice(ws: WebSocket):
    await ws.accept()
    if not ELEVENLABS_API_KEY or not ELEVENLABS_VOICE_ID:
        await ws.send_text(json.dumps({"type": "error", "message": "ElevenLabs not configured. Set ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID in .env"}))
        await ws.close()
        return

    api_key, _ = get_elevenlabs_config()

    eleven_url = (
        "wss://api.elevenlabs.io/v1/speech-to-text/realtime"
        "?model_id=scribe_v2_realtime"
        "&audio_format=pcm_16000"
        "&commit_strategy=vad"
        "&language_code=en"
        "&include_timestamps=false"
    )

    # websockets expects dict OR list[tuple], varies by version
    header_dict = {"xi-api-key": api_key}
    header_list = [("xi-api-key", api_key)]

    try:
        # ---- Connect to ElevenLabs with version-compatible headers ----
        try:
            # websockets >= 12 often uses additional_headers
            el_ws = await websockets.connect(eleven_url, additional_headers=header_dict)
        except TypeError:
            try:
                # some versions use extra_headers
                el_ws = await websockets.connect(eleven_url, extra_headers=header_list)
            except TypeError:
                # older versions may accept "headers"
                el_ws = await websockets.connect(eleven_url, headers=header_list)

        async with el_ws:

            async def forward_audio():
                while True:
                    data = await ws.receive_bytes()
                    b64 = base64.b64encode(data).decode("ascii")
                    print("got bytes:", len(data))
                    msg = {
                        "message_type": "input_audio_chunk",
                        "audio_base_64": b64,
                        "sample_rate": 16000,
                    }
                    await el_ws.send(json.dumps(msg))

            async def forward_transcripts():
                async for message in el_ws:
                    try:
                        payload = json.loads(message)
                    except Exception:
                        continue

                    mt = payload.get("message_type")
                    if mt in (
                        "partial_transcript",
                        "committed_transcript",
                        "committed_transcript_with_timestamps",
                        "session_started",
                    ):
                        await ws.send_json(payload)
                    elif mt and "error" in mt or "error" in payload:
                        await ws.send_json(payload)

            await asyncio.gather(forward_audio(), forward_transcripts())

    except WebSocketDisconnect:
        return
    except Exception as e:
        # send back full error so you see it in browser console
        try:
            await ws.send_json({"message_type": "server_error", "detail": repr(e)})
        except Exception:
            pass


@app.get("/health")
async def health_check():
    return {"status": "healthy", "message": "Service is running"}


if __name__ == "__main__":
     import uvicorn
     result = get_elevenlabs_config()
     print(result)
     print("Starting PDF Upload API server...")
     uvicorn.run(app, host="0.0.0.0", port=8000)
