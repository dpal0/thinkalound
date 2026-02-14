import os
import json
import asyncio
import base64
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import websockets
import httpx

load_dotenv()

ELEVENLABS_API_KEY = os.environ["ELEVENLABS_API_KEY"]
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "")

app = FastAPI()

# ----- Config -----
# ElevenLabs realtime STT websocket (per docs)
ELEVEN_STT_WS_URL = "wss://api.elevenlabs.io/v1/speech-to-text/realtime"
# ElevenLabs TTS streaming REST endpoint (per docs)
ELEVEN_TTS_STREAM_URL = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}/stream"

HEADERS = {
    "xi-api-key": ELEVENLABS_API_KEY,
}

@app.websocket("/ws/voice")
async def ws_voice(ws: WebSocket):
    await ws.accept()

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
