// app.js
const API_URL = "http://localhost:8000";

let conversationId = null;
let chatStarted = false;

const fileInput = document.getElementById("fileInput");
const choosePdfBtn = document.getElementById("choosePdfBtn");
const statusEl = document.getElementById("status");
const messagesEl = document.getElementById("messages");
const chatInput = document.getElementById("chatInput");
const sendBtn = document.getElementById("sendBtn");

const ttsAudio = document.getElementById("ttsAudio");
function mustGet(id) {
  const el = document.getElementById(id);
  if (!el) throw new Error(`Missing element with id="${id}" in HTML`);
  return el;
}
const micPlayback = mustGet("micPlayback");
const recordStatus = mustGet("recordStatus");
const startRecBtn = mustGet("startRecBtn");
const stopRecBtn = mustGet("stopRecBtn");

let lastAudioUrl = null;

// -------------------------
// UI event wiring
// -------------------------
choosePdfBtn.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", handleFile);

sendBtn.addEventListener("click", sendMessage);
chatInput.addEventListener("keypress", (e) => {
  if (e.key === "Enter") sendMessage();
});

// -------------------------
// TTS
// -------------------------
async function playTTS(text) {
  const clean = (text || "").trim();
  if (!clean) return;

  try {
    const res = await fetch(`${API_URL}/api/tts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: clean }),
    });

    if (!res.ok) {
      console.error("TTS failed:", await res.text());
      return;
    }

    const blob = await res.blob(); // audio/mpeg
    const url = URL.createObjectURL(blob);

    if (lastAudioUrl) URL.revokeObjectURL(lastAudioUrl);
    lastAudioUrl = url;

    ttsAudio.src = url;

    // Browser autoplay rules: this will work after a user gesture (click Send / Choose PDF).
    await ttsAudio.play();
  } catch (err) {
    console.error("TTS error:", err);
  }
}

// -------------------------
// Upload PDF
// -------------------------
async function handleFile() {
  const file = fileInput.files[0];
  if (!file) return;

  statusEl.textContent = "Uploading...";

  const formData = new FormData();
  formData.append("file", file);

  try {
    const response = await fetch(`${API_URL}/upload-pdf`, {
      method: "POST",
      body: formData,
    });

    const result = await response.json();

    if (!response.ok || !result.success) {
      statusEl.textContent = "Upload failed";
      console.error(result);
      return;
    }

    conversationId = result.conversation_id;
    statusEl.textContent = "Upload successful!";
    await startChat(); // start chat will fetch first question + play TTS
  } catch (error) {
    statusEl.textContent = "Upload error";
    console.error(error);
  }
}

// -------------------------
// Start chat (get first question)
// -------------------------
async function startChat() {
  try {
    const response = await fetch(`${API_URL}/start-chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_id: conversationId }),
    });

    const result = await response.json();

    if (!response.ok || !result.success) {
      console.error("start-chat failed:", result);
      return;
    }

    chatStarted = true;
    addMessage(result.question, "ai");
    await playTTS(result.question);
  } catch (error) {
    console.error(error);
  }
}

// -------------------------
// Send message
// -------------------------
async function sendMessage() {
  const message = chatInput.value.trim();
  if (!message) return;

  if (!chatStarted) {
    addMessage("Please upload a resume first", "ai");
    return;
  }

  addMessage(message, "user");
  chatInput.value = "";

  try {
    const response = await fetch(`${API_URL}/send-message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        conversation_id: conversationId,
        message: message,
      }),
    });

    const result = await response.json();

    if (!response.ok || !result.success) {
      addMessage("Error sending message", "ai");
      console.error("send-message failed:", result);
      return;
    }

    if (result.ai_response) {
      addMessage(result.ai_response, "ai");
      await playTTS(result.ai_response);
    }

    if (result.next_question) {
      // Slight delay to feel conversational
      setTimeout(async () => {
        addMessage(result.next_question, "ai");
        await playTTS(result.next_question);
      }, 800);
    }
  } catch (error) {
    addMessage("Error sending message", "ai");
    console.error(error);
  }
}

// -------------------------
// Render message bubble
// -------------------------
function addMessage(text, type) {
  const div = document.createElement("div");
  div.className = `message ${type}`;
  div.textContent = text;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

// Speech to Text
// -------------------------
// // Local mic record + playback (debug)
// let recAudioCtx = null;
// let recSourceNode = null;
// let recProcessorNode = null;
// let recMediaStream = null;

// let recordedPCM16Chunks = [];
// let isRecording = false;

// startRecBtn.addEventListener("click", startLocalRecording);
// stopRecBtn.addEventListener("click", stopLocalRecording);

// function downsampleBuffer(buffer, inputSampleRate, outputSampleRate) {
//   if (outputSampleRate === inputSampleRate) return buffer;
//   const ratio = inputSampleRate / outputSampleRate;
//   const newLength = Math.round(buffer.length / ratio);
//   const result = new Float32Array(newLength);
//   let offsetResult = 0;
//   let offsetBuffer = 0;

//   while (offsetResult < result.length) {
//     const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio);
//     let sum = 0;
//     let count = 0;
//     for (let i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i++) {
//       sum += buffer[i];
//       count++;
//     }
//     result[offsetResult] = sum / count;
//     offsetResult++;
//     offsetBuffer = nextOffsetBuffer;
//   }
//   return result;
// }

// function floatTo16BitPCM(float32Array) {
//   const buf = new ArrayBuffer(float32Array.length * 2);
//   const view = new DataView(buf);
//   for (let i = 0; i < float32Array.length; i++) {
//     let s = Math.max(-1, Math.min(1, float32Array[i]));
//     view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
//   }
//   return buf;
// }

// function concatArrayBuffers(buffers) {
//   let total = 0;
//   for (const b of buffers) total += b.byteLength;
//   const out = new Uint8Array(total);
//   let offset = 0;
//   for (const b of buffers) {
//     out.set(new Uint8Array(b), offset);
//     offset += b.byteLength;
//   }
//   return out.buffer;
// }

// function writeString(view, offset, str) {
//   for (let i = 0; i < str.length; i++) {
//     view.setUint8(offset + i, str.charCodeAt(i));
//   }
// }

// function makeWavFromPCM16(pcm16Buffer, sampleRate = 16000, numChannels = 1) {
//   const bytesPerSample = 2;
//   const blockAlign = numChannels * bytesPerSample;
//   const byteRate = sampleRate * blockAlign;
//   const dataSize = pcm16Buffer.byteLength;

//   const headerSize = 44;
//   const wavBuffer = new ArrayBuffer(headerSize + dataSize);
//   const view = new DataView(wavBuffer);

//   writeString(view, 0, "RIFF");
//   view.setUint32(4, 36 + dataSize, true);
//   writeString(view, 8, "WAVE");

//   writeString(view, 12, "fmt ");
//   view.setUint32(16, 16, true);
//   view.setUint16(20, 1, true);
//   view.setUint16(22, numChannels, true);
//   view.setUint32(24, sampleRate, true);
//   view.setUint32(28, byteRate, true);
//   view.setUint16(32, blockAlign, true);
//   view.setUint16(34, 16, true);

//   writeString(view, 36, "data");
//   view.setUint32(40, dataSize, true);

//   new Uint8Array(wavBuffer, 44).set(new Uint8Array(pcm16Buffer));
//   return wavBuffer;
// }

// async function startLocalRecording() {
//   startRecBtn.disabled = true;
//   stopRecBtn.disabled = false;

//   recordStatus.textContent = "Recording...";
//   recordedPCM16Chunks = [];
//   isRecording = true;

//   recMediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
//   recAudioCtx = new (window.AudioContext || window.webkitAudioContext)();

//   console.log("AudioContext sampleRate:", recAudioCtx.sampleRate);

//   recSourceNode = recAudioCtx.createMediaStreamSource(recMediaStream);
//   recProcessorNode = recAudioCtx.createScriptProcessor(4096, 1, 1);

//   let frames = 0;
//   recProcessorNode.onaudioprocess = (e) => {
//     if (!isRecording) return;

//     frames++;
//     if (frames % 20 === 0) console.log("onaudioprocess frames:", frames);

//     const input = e.inputBuffer.getChannelData(0);
//     const downsampled = downsampleBuffer(input, recAudioCtx.sampleRate, 16000);
//     const pcm16 = floatTo16BitPCM(downsampled);
//     recordedPCM16Chunks.push(pcm16);
//   };

//   // IMPORTANT: connect through gain=0 so the processor runs, without feedback
//   const gain = recAudioCtx.createGain();
//   gain.gain.value = 0;

//   recSourceNode.connect(recProcessorNode);
//   recProcessorNode.connect(gain);
//   gain.connect(recAudioCtx.destination);
// }

// async function stopLocalRecording() {
//   isRecording = false;
//   stopRecBtn.disabled = true;
//   startRecBtn.disabled = false;

//   recordStatus.textContent = "Stopped. Building WAV...";

//   try {
//     if (recProcessorNode) recProcessorNode.disconnect();
//     if (recSourceNode) recSourceNode.disconnect();

//     if (recMediaStream) recMediaStream.getTracks().forEach((t) => t.stop());
//     if (recAudioCtx) await recAudioCtx.close();

//     console.log("Recorded chunks:", recordedPCM16Chunks.length);

//     const pcm16Buffer = concatArrayBuffers(recordedPCM16Chunks);
//     console.log("PCM16 bytes:", pcm16Buffer.byteLength);

//     const wavBuffer = makeWavFromPCM16(pcm16Buffer, 16000, 1);
//     const wavBlob = new Blob([wavBuffer], { type: "audio/wav" });

//     recordStatus.textContent = `Playback ready. Size: ${wavBlob.size} bytes`;

//     const url = URL.createObjectURL(wavBlob);
//     micPlayback.src = url;

//     await micPlayback.play();
//   } catch (e) {
//     console.error(e);
//     recordStatus.textContent = "Error building or playing WAV (check console).";
//   } finally {
//     recAudioCtx = null;
//     recSourceNode = null;
//     recProcessorNode = null;
//     recMediaStream = null;
//   }
// }

// -------------------------
// Unified Voice: record + playback + STT streaming
// -------------------------
let voiceAudioCtx = null;
let voiceSourceNode = null;
let voiceProcessorNode = null;
let voiceMediaStream = null;
let sttSocket = null;

let recordedPCM16Chunks = [];
let isRecording = false;

const liveTranscript = mustGet("liveTranscript");

startRecBtn.addEventListener("click", startVoice);
stopRecBtn.addEventListener("click", stopVoice);

function downsampleBuffer(buffer, inputSampleRate, outputSampleRate) {
  if (outputSampleRate === inputSampleRate) return buffer;
  const ratio = inputSampleRate / outputSampleRate;
  const newLength = Math.round(buffer.length / ratio);
  const result = new Float32Array(newLength);
  let offsetResult = 0;
  let offsetBuffer = 0;

  while (offsetResult < result.length) {
    const nextOffsetBuffer = Math.round((offsetResult + 1) * ratio);
    let sum = 0;
    let count = 0;
    for (let i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i++) {
      sum += buffer[i];
      count++;
    }
    result[offsetResult] = sum / count;
    offsetResult++;
    offsetBuffer = nextOffsetBuffer;
  }
  return result;
}

function floatTo16BitPCM(float32Array) {
  const buf = new ArrayBuffer(float32Array.length * 2);
  const view = new DataView(buf);
  for (let i = 0; i < float32Array.length; i++) {
    let s = Math.max(-1, Math.min(1, float32Array[i]));
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return buf;
}

function concatArrayBuffers(buffers) {
  let total = 0;
  for (const b of buffers) total += b.byteLength;
  const out = new Uint8Array(total);
  let offset = 0;
  for (const b of buffers) {
    out.set(new Uint8Array(b), offset);
    offset += b.byteLength;
  }
  return out.buffer;
}

function writeString(view, offset, str) {
  for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
}

function makeWavFromPCM16(pcm16Buffer, sampleRate = 16000, numChannels = 1) {
  const bytesPerSample = 2;
  const blockAlign = numChannels * bytesPerSample;
  const byteRate = sampleRate * blockAlign;
  const dataSize = pcm16Buffer.byteLength;

  const wavBuffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(wavBuffer);

  writeString(view, 0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeString(view, 8, "WAVE");

  writeString(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, 16, true);

  writeString(view, 36, "data");
  view.setUint32(40, dataSize, true);

  new Uint8Array(wavBuffer, 44).set(new Uint8Array(pcm16Buffer));
  return wavBuffer;
}

async function startVoice() {
  startRecBtn.disabled = true;
  stopRecBtn.disabled = false;

  recordStatus.textContent = "Recording + STT streaming...";
  liveTranscript.textContent = "";
  recordedPCM16Chunks = [];
  isRecording = true;

  // 1) Connect STT WebSocket to YOUR backend
  sttSocket = new WebSocket("ws://localhost:8000/ws/stt");
  sttSocket.binaryType = "arraybuffer";

  sttSocket.onopen = () => console.log("STT socket opened");
  sttSocket.onerror = (e) => console.error("STT socket error", e);
  sttSocket.onclose = () => console.log("STT socket closed");

  sttSocket.onmessage = (event) => {
    let payload;
    try { payload = JSON.parse(event.data); } catch { return; }

    if (payload.message_type === "partial_transcript") {
      liveTranscript.textContent = payload.text || "";
    }
    if (payload.message_type === "committed_transcript") {
      const t = payload.text || "";
      if (t.trim()) {
        // Put final transcript into chat input, or auto-send
        chatInput.value = t;
        // Optional: add to messages
        // addMessage(t, "user");
      }
    }
    if (payload.message_type === "server_error") {
      console.error("Server error:", payload.detail);
    }
  };

  // 2) Start mic capture
  voiceMediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  voiceAudioCtx = new (window.AudioContext || window.webkitAudioContext)();

  console.log("AudioContext sampleRate:", voiceAudioCtx.sampleRate);

  voiceSourceNode = voiceAudioCtx.createMediaStreamSource(voiceMediaStream);
  voiceProcessorNode = voiceAudioCtx.createScriptProcessor(4096, 1, 1);

  // ensure processor runs without feedback:
  const gain = voiceAudioCtx.createGain();
  gain.gain.value = 0;

  voiceProcessorNode.onaudioprocess = (e) => {
    if (!isRecording) return;

    const input = e.inputBuffer.getChannelData(0);
    const downsampled = downsampleBuffer(input, voiceAudioCtx.sampleRate, 16000);
    const pcm16 = floatTo16BitPCM(downsampled);

    // A) store for local playback
    recordedPCM16Chunks.push(pcm16);

    // B) stream to backend -> ElevenLabs STT
    if (sttSocket && sttSocket.readyState === 1) {
      sttSocket.send(pcm16);
    }
  };

  voiceSourceNode.connect(voiceProcessorNode);
  voiceProcessorNode.connect(gain);
  gain.connect(voiceAudioCtx.destination);
}

async function stopVoice() {
  isRecording = false;
  stopRecBtn.disabled = true;
  startRecBtn.disabled = false;

  recordStatus.textContent = "Stopped.";

  try {
    if (voiceProcessorNode) voiceProcessorNode.disconnect();
    if (voiceSourceNode) voiceSourceNode.disconnect();

    if (voiceMediaStream)
      voiceMediaStream.getTracks().forEach((t) => t.stop());

    if (voiceAudioCtx)
      await voiceAudioCtx.close();

    if (sttSocket && sttSocket.readyState === 1)
      sttSocket.close();

  } catch (e) {
    console.error(e);
    recordStatus.textContent = "Error stopping voice.";
  } finally {
    voiceAudioCtx = null;
    voiceSourceNode = null;
    voiceProcessorNode = null;
    voiceMediaStream = null;
    sttSocket = null;
  }
}


