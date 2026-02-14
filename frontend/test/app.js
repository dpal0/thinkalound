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
