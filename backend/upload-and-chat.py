from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import PyPDF2
import io
import json
from typing import List, Dict, Any
import openai
import os
from datetime import datetime

app = FastAPI()

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend files
app.mount("/static", StaticFiles(directory="../frontend"), name="static")

# In-memory storage for demo (use database in production)
resume_data = {}
conversation_history = {}

class ChatMessage(BaseModel):
    message: str
    conversation_id: str

class ChatResponse(BaseModel):
    response: str
    question: str
    conversation_id: str

@app.get("/")
async def root():
    return {"message": "Resume Voice Chat API"}

@app.post("/upload-resume")
async def upload_resume(file: UploadFile = File(...)):
    """
    Upload and process PDF resume
    """
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    
    try:
        # Read PDF content
        content = await file.read()
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))
        
        # Extract text from all pages
        text = ""
        for page_num in range(len(pdf_reader.pages)):
            page = pdf_reader.pages[page_num]
            text += page.extract_text() + "\n"
        
        if not text.strip():
            raise HTTPException(status_code=400, detail="Could not extract text from PDF")
        
        # Generate a simple conversation ID
        conversation_id = f"conv_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Store resume data
        resume_data[conversation_id] = {
            "filename": file.filename,
            "content": text,
            "upload_time": datetime.now().isoformat()
        }
        
        # Initialize conversation history
        conversation_history[conversation_id] = []
        
        return {
            "success": True,
            "message": "Resume uploaded successfully",
            "conversation_id": conversation_id,
            "text_preview": text[:500] + "..." if len(text) > 500 else text,
            "text_length": len(text)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")

@app.post("/start-conversation")
async def start_conversation(conversation_id: str):
    """
    Start conversation and generate first question
    """
    if conversation_id not in resume_data:
        raise HTTPException(status_code=404, detail="Resume not found")
    
    resume_content = resume_data[conversation_id]["content"]
    
    # Generate first question based on resume
    first_question = generate_question_from_resume(resume_content, [])
    
    # Add to conversation history
    conversation_history[conversation_id].append({
        "type": "ai_question",
        "content": first_question,
        "timestamp": datetime.now().isoformat()
    })
    
    return {
        "question": first_question,
        "conversation_id": conversation_id,
        "message": "Conversation started"
    }

@app.post("/chat", response_model=ChatResponse)
async def chat(chat_data: ChatMessage):
    """
    Handle user response and generate next question
    """
    conversation_id = chat_data.conversation_id
    user_message = chat_data.message
    
    if conversation_id not in resume_data:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Add user response to history
    conversation_history[conversation_id].append({
        "type": "user_response",
        "content": user_message,
        "timestamp": datetime.now().isoformat()
    })
    
    resume_content = resume_data[conversation_id]["content"]
    conversation = conversation_history[conversation_id]
    
    # Generate response and next question
    response = generate_response_to_user(user_message, resume_content, conversation)
    next_question = generate_question_from_resume(resume_content, conversation)
    
    # Add AI response to history
    conversation_history[conversation_id].append({
        "type": "ai_response",
        "content": response,
        "timestamp": datetime.now().isoformat()
    })
    
    conversation_history[conversation_id].append({
        "type": "ai_question",
        "content": next_question,
        "timestamp": datetime.now().isoformat()
    })
    
    return ChatResponse(
        response=response,
        question=next_question,
        conversation_id=conversation_id
    )

@app.get("/conversation/{conversation_id}")
async def get_conversation(conversation_id: str):
    """
    Get conversation history
    """
    if conversation_id not in conversation_history:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return {
        "conversation_id": conversation_id,
        "history": conversation_history[conversation_id],
        "resume_info": {
            "filename": resume_data[conversation_id]["filename"],
            "upload_time": resume_data[conversation_id]["upload_time"]
        }
    }

def generate_question_from_resume(resume_content: str, conversation_history: List[Dict]) -> str:
    """
    Generate interview questions based on resume content
    For now, using simple logic - you can integrate OpenAI/Claude here
    """
    
    # Simple question bank - in production, use AI to generate contextual questions
    questions = [
        "Tell me about your most recent work experience and what you accomplished there.",
        "What programming languages or technologies are you most comfortable with?",
        "Describe a challenging project you worked on and how you overcame obstacles.",
        "What interests you most about this type of role?",
        "How do you stay updated with new technologies in your field?",
        "Tell me about a time you had to learn something completely new for a project.",
        "What are your career goals for the next few years?",
        "Describe your experience working in a team environment.",
        "What's a project or achievement you're particularly proud of?",
        "How do you approach problem-solving when faced with a difficult technical challenge?"
    ]
    
    # Filter out questions that have already been asked
    asked_questions = [entry["content"] for entry in conversation_history if entry["type"] == "ai_question"]
    available_questions = [q for q in questions if q not in asked_questions]
    
    if not available_questions:
        return "Thank you for sharing! Do you have any questions about the role or our company?"
    
    # For demo, return first available question
    # In production, use AI to pick most relevant question based on resume + conversation
    return available_questions[0]

def generate_response_to_user(user_message: str, resume_content: str, conversation: List[Dict]) -> str:
    """
    Generate a response to user's answer
    For now, simple acknowledgment - you can add AI here
    """
    
    responses = [
        "That's great! Thanks for sharing that insight.",
        "Interesting! I can see how that experience would be valuable.",
        "Thanks for elaborating on that. That's really helpful context.",
        "I appreciate you walking me through that experience.",
        "That sounds like valuable experience. Thanks for the details."
    ]
    
    import random
    return random.choice(responses)

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "resume-chat-api"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)