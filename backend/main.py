import os
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

load_dotenv()

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

# ----- Config -----
# ElevenLabs realtime STT websocket (per docs)
ELEVEN_STT_WS_URL = "wss://api.elevenlabs.io/v1/speech-to-text/realtime"
# ElevenLabs TTS streaming REST endpoint (per docs)
ELEVEN_TTS_STREAM_URL = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}/stream"

HEADERS = {
    "xi-api-key": ELEVENLABS_API_KEY,
}


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

    # Connect to ElevenLabs realtime STT
    # You may need to pass query params depending on your audio format.
    # We'll use 16kHz mono PCM16 from browser via AudioWorklet (recommended).
    try:
        async with websockets.connect(
            ELEVEN_STT_WS_URL,
            extra_headers=HEADERS,
            ping_interval=20,
            ping_timeout=20,
        ) as stt_ws:

            # Send an initial config message if required by ElevenLabs STT
            # Some providers require this; if ElevenLabs expects it, add it here.
            # We'll keep it minimal and adapt once you see the first error payload.
            await stt_ws.send(json.dumps({
                "type": "start",
                "audio_format": {
                    "type": "pcm_s16le",
                    "sample_rate": 16000,
                    "channels": 1
                }
            }))

            async def forward_audio():
                """Client -> Eleven STT"""
                while True:
                    msg = await ws.receive_text()
                    data = json.loads(msg)

                    if data["type"] == "audio":
                        # audio is base64 PCM16 chunk
                        await stt_ws.send(json.dumps({
                            "type": "audio",
                            "audio": data["audio"]
                        }))
                    elif data["type"] == "stop":
                        await stt_ws.send(json.dumps({"type": "stop"}))
                        break

            async def read_transcripts_and_respond():
                """Eleven STT -> client transcript; and trigger TTS on final transcript."""
                buffer_text = ""
                while True:
                    raw = await stt_ws.recv()
                    event = json.loads(raw)

                    # You will inspect actual event schema once you run it.
                    # We'll handle common shapes: partial + final.
                    if event.get("type") in ("partial_transcript", "transcript"):
                        text = event.get("text", "")
                        is_final = event.get("is_final", False)

                        # Stream transcript to frontend
                        await ws.send_text(json.dumps({
                            "type": "transcript",
                            "text": text,
                            "is_final": is_final
                        }))

                        if is_final and text.strip():
                            # For hackathon MVP: simple echo response
                            reply = f"Got it. You said: {text.strip()}"
                            await ws.send_text(json.dumps({"type": "llm_text", "text": reply}))

                            # Stream TTS audio back
                            async for chunk_b64 in stream_tts_b64(reply):
                                await ws.send_text(json.dumps({
                                    "type": "tts_audio",
                                    "audio": chunk_b64
                                }))

                            await ws.send_text(json.dumps({"type": "tts_done"}))

                    elif event.get("type") == "end":
                        break

            async def stream_tts_b64(text: str):
                """Calls ElevenLabs TTS streaming endpoint and yields base64 audio chunks."""
                if not ELEVENLABS_VOICE_ID:
                    # If no voice id, just skip
                    return

                payload = {
                    "text": text,
                    # model_id optional; you can set a low-latency model if your account supports it
                    # "model_id": "eleven_flash_v2",
                    "voice_settings": {"stability": 0.4, "similarity_boost": 0.8}
                }

                async with httpx.AsyncClient(timeout=None) as client:
                    with client.stream("POST", ELEVEN_TTS_STREAM_URL, headers=HEADERS, json=payload) as r:
                        r.raise_for_status()
                        async for chunk in r.aiter_bytes():
                            if not chunk:
                                continue
                            yield base64.b64encode(chunk).decode("utf-8")

            await asyncio.gather(forward_audio(), read_transcripts_and_respond())

    except WebSocketDisconnect:
        return
    except Exception as e:
        # send error to frontend for debugging
        try:
            await ws.send_text(json.dumps({"type": "error", "message": str(e)}))
        except:
            pass
        return
