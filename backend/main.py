from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import PyPDF2
import io
import random
from datetime import datetime
from typing import List, Dict

app = FastAPI()

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage for conversations (use database in production)
conversations = {}

# Pydantic models for request/response
class ChatMessage(BaseModel):
    conversation_id: str
    message: str

@app.get("/")
async def root():
    return {"message": "PDF Upload API is running!"}

@app.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    """
    Upload and extract text from PDF
    """
    print(f"Received file: {file.filename}")
    
    # Check if it's a PDF
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    
    try:
        # Read the file content
        content = await file.read()
        print(f"File size: {len(content)} bytes")
        
        # Extract text from PDF
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))
        print(f"Number of pages: {len(pdf_reader.pages)}")
        
        # Extract text from all pages
        extracted_text = ""
        for page_num, page in enumerate(pdf_reader.pages):
            page_text = page.extract_text()
            extracted_text += page_text + "\n"
            print(f"Page {page_num + 1}: {len(page_text)} characters")
        
        if not extracted_text.strip():
            raise HTTPException(status_code=400, detail="Could not extract text from PDF. The PDF might be image-based or corrupted.")
        
        print(f"Total extracted text: {len(extracted_text)} characters")
        
        # Generate conversation ID and store the resume
        conversation_id = f"conv_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{random.randint(1000, 9999)}"
        conversations[conversation_id] = {
            "resume_text": extracted_text,
            "messages": [],
            "created_at": datetime.now().isoformat()
        }
        
        return {
            "success": True,
            "message": "PDF processed successfully!",
            "filename": file.filename,
            "text_length": len(extracted_text),
            "text_preview": extracted_text[:500],  # First 500 characters
            "conversation_id": conversation_id
        }
        
    except Exception as e:
        print(f"Error processing PDF: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")


class StartChatRequest(BaseModel):
    conversation_id: str

@app.post("/start-chat")
async def start_chat(request: StartChatRequest):
    """Start conversation with first question"""
    if request.conversation_id not in conversations:
        raise HTTPException(status_code=400, detail="Conversation not found")
    
    # Generate first question based on resume
    resume_text = conversations[request.conversation_id]["resume_text"]
    first_question = generate_question(resume_text, conversations[request.conversation_id]["messages"])
    
    # Add first question to conversation
    conversations[request.conversation_id]["messages"].append({
        "type": "ai_question",
        "content": first_question,
        "timestamp": datetime.now().isoformat()
    })
    
    return {
        "success": True,
        "question": first_question,
        "conversation_id": request.conversation_id
    }

@app.post("/send-message")
async def send_message(chat_data: ChatMessage):
    """
    Handle user message and generate response
    """
    if chat_data.conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    conversation = conversations[chat_data.conversation_id]
    
    # Add user message
    conversation["messages"].append({
        "type": "user_response",
        "content": chat_data.message,
        "timestamp": datetime.now().isoformat()
    })
    
    # Generate AI response
    ai_response = generate_response(chat_data.message)
    conversation["messages"].append({
        "type": "ai_response", 
        "content": ai_response,
        "timestamp": datetime.now().isoformat()
    })
    
    # Generate next question
    next_question = generate_question(conversation["resume_text"], conversation["messages"])
    if next_question:
        conversation["messages"].append({
            "type": "ai_question",
            "content": next_question, 
            "timestamp": datetime.now().isoformat()
        })
    
    return {
        "success": True,
        "ai_response": ai_response,
        "next_question": next_question,
        "conversation_id": chat_data.conversation_id
    }

@app.get("/conversation/{conversation_id}")
async def get_conversation(conversation_id: str):
    """
    Get full conversation history
    """
    if conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return {
        "success": True,
        "conversation": conversations[conversation_id]
    }

def generate_question(resume_text: str, conversation_history: List[Dict]) -> str:
    """
    Generate interview questions - you can make this smarter with AI later
    """
    # Basic question bank
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
        "What's the most innovative solution you've implemented?"
    ]
    
    # Get already asked questions
    asked_questions = [msg["content"] for msg in conversation_history if msg["type"] == "ai_question"]
    
    # Filter available questions
    available_questions = [q for q in questions if q not in asked_questions]
    
    if not available_questions:
        return "Thank you for sharing! Do you have any questions about the role or our company?"
    
    # Return a random available question
    return random.choice(available_questions)

def generate_response(user_message: str) -> str:
    """
    Generate AI response to user's answer - you can make this smarter with AI later
    """
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
        "I can tell you've put thought into your career development."
    ]
    
    return random.choice(responses)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "message": "PDF Upload service is running"}

if __name__ == "__main__":
    import uvicorn
    print("Starting PDF Upload API server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)