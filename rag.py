# fastapi_app.py

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from dotenv import load_dotenv
import os, tempfile, uuid
from pinecone import Pinecone
from langchain_community.embeddings import HuggingFaceEmbeddings
import google.generativeai as genai

load_dotenv()

app = FastAPI(title="README Chatbot API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pinecone_client = None
index_name = "index1"
index_dimensions = 1024

# Models
embedding_model = HuggingFaceEmbeddings(model_name="sentence-transformers/all-roberta-large-v1")
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def chunk_text(text, chunk_size=1000, overlap=200):
    chunks, start, text_length = [], 0, len(text)
    while start < text_length:
        end = min(start + chunk_size, text_length)
        last_period = text.rfind('.', start, end)
        last_newline = text.rfind('\n', start, end)
        if last_period > start + chunk_size // 2:
            end = last_period + 1
        elif last_newline > start + chunk_size // 2:
            end = last_newline + 1
        chunks.append(text[start:end])
        start = end - overlap if end < text_length else text_length
    return chunks

def embed_chunks(chunks):
    return [embedding_model.embed_documents([chunk])[0] for chunk in chunks]

def init_pinecone():
    global pinecone_client
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        raise ValueError("Missing Pinecone API Key")
    pinecone_client = Pinecone(api_key=api_key)
    if index_name not in [idx.name for idx in pinecone_client.list_indexes()]:
        raise ValueError(f"Index '{index_name}' not found")
    return pinecone_client.Index(index_name)

@app.post("/upload")
async def upload_readme(file: UploadFile = File(...)):
    temp_path = tempfile.mktemp(suffix=".md")
    with open(temp_path, "wb") as f:
        f.write(await file.read())
    with open(temp_path, "r", encoding="utf-8") as f:
        text = f.read()
    os.unlink(temp_path)

    chunks = chunk_text(text)
    embeddings = embed_chunks(chunks)
    index = init_pinecone()

    for i in range(0, len(chunks), 100):
        i_end = min(i + 100, len(chunks))
        ids = [f"{file.filename}-{uuid.uuid4()}" for _ in range(i, i_end)]
        metadata = [{"text": chunks[j], "file_name": file.filename, "chunk_id": j} for j in range(i, i_end)]
        vectors = [(ids[j-i], embeddings[j], metadata[j-i]) for j in range(i, i_end)]
        index.upsert(vectors=vectors)

    return JSONResponse(content={"message": f"Successfully processed {file.filename}"})

@app.post("/ask")
async def ask_question(query: str = Form(...), file_name: str = Form(...)):
    index = init_pinecone()
    query_embedding = embedding_model.embed_query(query)
    matches = index.query(vector=query_embedding, top_k=3, include_metadata=True, filter={"file_name": file_name})
    context = "\n\n".join([match.metadata["text"] for match in matches.matches])
    prompt = f"""
    Context:
    {context}

    Question: {query}
    Provide a concise and helpful answer in well-formatted Markdown.
    """
    model = genai.GenerativeModel("gemini-2.0-flash")
    response = model.generate_content(prompt, generation_config={"temperature": 0.7})
    return JSONResponse(content={"response": response.text})

@app.get("/")
def ui():
    return HTMLResponse("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>README Chatbot</title>
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap">
        <style>
            body {
                font-family: 'Roboto', sans-serif;
                margin: 0;
                background-color: #f4f7f6;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
            }
            .container {
                background-color: #fff;
                border-radius: 8px;
                box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
                overflow: hidden;
                width: 90%;
                max-width: 800px;
                padding: 20px;
                display: flex;
                flex-direction: column;
            }
            h2 {
                color: #333;
                text-align: center;
                margin-bottom: 20px;
            }
            #upload-section, #chat-section {
                margin-bottom: 20px;
                padding: 15px;
                border-radius: 5px;
                border: 1px solid #e0e0e0;
                background-color: #fff;
            }
            #upload-section h3, #chat-section h3 {
                color: #555;
                margin-top: 0;
                margin-bottom: 10px;
            }
            #upload-form input[type="file"] {
                display: block;
                width: 100%;
                padding: 10px;
                margin-bottom: 10px;
                border: 1px solid #ccc;
                border-radius: 4px;
                box-sizing: border-box;
            }
            #upload-form button {
                background-color: #007bff;
                color: white;
                padding: 10px 15px;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 1rem;
                transition: background-color 0.3s ease;
            }
            #upload-form button:disabled {
                background-color: #ccc;
                cursor: not-allowed;
            }
            #upload-form button:hover:enabled {
                background-color: #0056b3;
            }
            #chat-container {
                flex-grow: 1;
                overflow-y: auto;
                padding: 10px;
                border: 1px solid #d0d0d0;
                border-radius: 5px;
                margin-bottom: 10px;
                display: flex;
                flex-direction: column;
                gap: 0.5rem;
                background-color: #f9f9f9;
            }
            .chat-message {
                padding: 10px 15px;
                border-radius: 8px;
                max-width: 80%;
                word-break: break-word;
            }
            .user-message {
                background-color: #e2f0ff;
                color: #1e3a8a;
                align-self: flex-end;
            }
            .bot-message {
                background-color: #f0f8ea;
                color: #155724;
                align-self: flex-start;
            }
            .bot-message pre {
                background-color: #e0e7de;
                padding: 0.75rem;
                border-radius: 4px;
                overflow-x: auto;
            }
            #chat-form {
                display: flex;
                gap: 10px;
            }
            #chat-form input[type="text"] {
                flex-grow: 1;
                padding: 10px;
                border: 1px solid #ccc;
                border-radius: 4px;
                box-sizing: border-box;
            }
            #chat-form button {
                background-color: #28a745;
                color: white;
                padding: 10px 15px;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                font-size: 1rem;
                transition: background-color 0.3s ease;
            }
            #chat-form button:disabled {
                background-color: #ccc;
                cursor: not-allowed;
            }
            #chat-form button:hover:enabled {
                background-color: #1e7e34;
            }
            .loading-spinner {
                border: 4px solid rgba(0, 0, 0, 0.1);
                border-top: 4px solid #3498db;
                border-radius: 50%;
                width: 20px;
                height: 20px;
                animation: spin 2s linear infinite;
                display: inline-block;
                margin-left: 5px;
            }
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            #upload-message {
                margin-top: 10px;
                font-size: 0.9rem;
                color: #5cb85c;
            }
        </style>
        <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    </head>
    <body>
        <div class="container">
            <h2>README Chatbot</h2>

            <section id="upload-section">
                <h3>Upload README</h3>
                <form id="upload-form" enctype="multipart/form-data" method="post">
                    <input type="file" name="file" accept=".md" required>
                    <button type="submit" id="upload-button">Upload</button>
                    <div id="upload-message" aria-live="polite"></div>
                </form>
            </section>

            <section id="chat-section">
                <h3>Chat with your README</h3>
                <div id="chat-container" aria-live="polite">
                    <div id="response-area"></div>
                </div>
                <form id="chat-form" method="post" onsubmit="sendMessage(event)">
                    <input type="text" id="query" name="query" placeholder="Ask your question about the README" required>
                    <input type="text" id="file_name" name="file_name" value="" placeholder="README filename" required>
                    <button type="submit" id="ask-button">Ask</button>
                </form>
            </section>
        </div>

        <script>
            const chatContainer = document.getElementById('response-area');
            const queryInput = document.getElementById('query');
            const fileNameInput = document.getElementById('file_name');
            const chatForm = document.getElementById('chat-form');
            const uploadForm = document.getElementById('upload-form');
            const uploadMessageDiv = document.getElementById('upload-message');
            const uploadButton = document.getElementById('upload-button');
            const askButton = document.getElementById('ask-button');

            uploadForm.addEventListener('submit', async (event) => {
                event.preventDefault();
                uploadButton.disabled = true;
                uploadButton.textContent = 'Uploading...';
                try {
                    const formData = new FormData(uploadForm);
                    const response = await fetch('/upload', {
                        method: 'POST',
                        body: formData
                    });
                    const data = await response.json();
                    uploadMessageDiv.textContent = data.message;
                } catch (error) {
                    uploadMessageDiv.textContent = 'Error uploading file.';
                    console.error('Error uploading file:', error);
                } finally {
                    uploadButton.disabled = false;
                    uploadButton.textContent = 'Upload';
                }
            });

            async function sendMessage(event) {
                event.preventDefault();
                const query = queryInput.value;
                const fileName = fileNameInput.value;
                if (!query || !fileName) {
                    alert('Please enter your question and the README filename.');
                    return;
                }

                askButton.disabled = true;
                askButton.textContent = 'Asking...';
                queryInput.disabled = true;
                fileNameInput.disabled = true;

                const userMessageDiv = document.createElement('div');
                userMessageDiv.classList.add('chat-message', 'user-message');
                userMessageDiv.textContent = query;
                chatContainer.appendChild(userMessageDiv);

                queryInput.value = ''; // Clear input field

                const formData = new FormData();
                formData.append('query', query);
                formData.append('file_name', fileName);

                try {
                    const response = await fetch('/ask', {
                        method: 'POST',
                        body: formData
                    });
                    const data = await response.json();
                    const botResponse = data.response;

                    const botMessageDiv = document.createElement('div');
                    botMessageDiv.classList.add('chat-message', 'bot-message');
                    botMessageDiv.innerHTML = marked.parse(botResponse); // Render Markdown

                    chatContainer.appendChild(botMessageDiv);
                    chatContainer.scrollTop = chatContainer.scrollHeight; // Scroll to bottom
                } catch (error) {
                    const errorMessageDiv = document.createElement('div');
                    errorMessageDiv.classList.add('bot-message');
                    errorMessageDiv.textContent = 'Error processing your question.';
                    chatContainer.appendChild(errorMessageDiv);
                    console.error('Error asking question:', error);
                } finally {
                    askButton.disabled = false;
                    askButton.textContent = 'Ask';
                    queryInput.disabled = false;
                    fileNameInput.disabled = false;
                }
            }
        </script>
    </body>
    </html>
    """)