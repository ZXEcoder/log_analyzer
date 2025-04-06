import streamlit as st
import os
import tempfile
import google.generativeai as genai
from pinecone import Pinecone
import uuid
from dotenv import load_dotenv
from langchain_community.embeddings import HuggingFaceEmbeddings


load_dotenv()

# Configuration
st.set_page_config(page_title="README Chatbot", layout="wide")

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "current_file_content" not in st.session_state:
    st.session_state.current_file_content = ""
if "current_file_name" not in st.session_state:
    st.session_state.current_file_name = ""
if "index_name" not in st.session_state:
    st.session_state.index_name = "index1"
if "is_initialized" not in st.session_state:
    st.session_state.is_initialized = False
if "index_dimensions" not in st.session_state:
    st.session_state.index_dimensions = 1024
if "pinecone_client" not in st.session_state:
    st.session_state.pinecone_client = None

# Functions for Markdown processing
def extract_text_from_markdown(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        text = f.read()
    return text

def chunk_text(text, chunk_size=1000, overlap=200):
    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = min(start + chunk_size, text_length)
        if end < text_length and end - start == chunk_size:
            # Find the last period or newline to make more natural chunks
            last_period = text.rfind('.', start, end)
            last_newline = text.rfind('\n', start, end)
            if last_period > start + chunk_size // 2:
                end = last_period + 1
            elif last_newline > start + chunk_size // 2:
                end = last_newline + 1

        chunks.append(text[start:end])
        start = end - overlap if end < text_length else text_length

    return chunks

# Embeddings and Vector Store functions (reused and adapted)
@st.cache_resource
def get_embedding_model():
    # Using a model that produces 1024-dimensional embeddings
    return HuggingFaceEmbeddings(model_name="sentence-transformers/all-roberta-large-v1")

def initialize_pinecone():
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        st.error("Pinecone API key not found. Please add it to your .env file as PINECONE_API_KEY=your_api_key")
        return False
    try:
        pc = Pinecone(api_key=api_key)
        st.session_state.pinecone_client = pc
        index_list = [idx.name for idx in pc.list_indexes()]
        if st.session_state.index_name not in index_list:
            st.error(f"Index '{st.session_state.index_name}' not found in your Pinecone account.")
            st.info("Available indexes: " + ", ".join(index_list))
            return False
        try:
            index = pc.Index(st.session_state.index_name)
            index_stats = index.describe_index_stats()
            if 'dimension' in index_stats:
                st.session_state.index_dimensions = index_stats['dimension']
                st.info(f"Detected index dimension: {st.session_state.index_dimensions}")
            else:
                st.warning("Could not detect index dimensions. Using default: 1024")
        except Exception as e:
            st.warning(f"Could not get index details: {str(e)}")
        return True
    except Exception as e:
        st.error(f"Error initializing Pinecone: {str(e)}")
        return False

def get_pinecone_index():
    if st.session_state.pinecone_client is None:
        st.error("Pinecone client not initialized.")
        return None
    return st.session_state.pinecone_client.Index(st.session_state.index_name)

def embed_chunks(chunks):
    model = get_embedding_model()
    embeddings = []
    for chunk in chunks:
        embed = model.embed_documents([chunk])[0]
        embeddings.append(embed)
    return embeddings

def store_embeddings(chunks, embeddings, file_name):
    index = get_pinecone_index()
    if index is None:
        return False
    batch_size = 100
    for i in range(0, len(chunks), batch_size):
        i_end = min(i + batch_size, len(chunks))
        ids = [f"{file_name}-{uuid.uuid4()}" for _ in range(i, i_end)]
        metadata = [{"text": chunks[j], "file_name": file_name, "chunk_id": j} for j in range(i, i_end)]
        vectors = [(ids[j-i], embeddings[j], metadata[j-i]) for j in range(i, i_end)]
        try:
            index.upsert(vectors=vectors)
            st.success(f"Successfully stored batch {i//batch_size + 1} of chunks to Pinecone")
        except Exception as e:
            st.error(f"Error storing embeddings: {str(e)}")
            return False
    st.success(f"Successfully stored all {len(chunks)} chunks to Pinecone")
    return True

def search_similar_chunks(query, top_k=5, file_name=None):
    model = get_embedding_model()
    query_embedding = model.embed_query(query)
    index = get_pinecone_index()
    if index is None:
        return []
    filter_query = {"file_name": file_name} if file_name else None
    results = index.query(
        vector=query_embedding,
        top_k=top_k,
        include_metadata=True,
        filter=filter_query
    )
    return results.matches

# Gemini LLM Integration (reused and adapted)
@st.cache_resource
def initialize_gemini():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        st.error("Google API key not found. Please add it to your .env file as GOOGLE_API_KEY=your_google_api_key")
        return False
    try:
        genai.configure(api_key=api_key)
        return True
    except Exception as e:
        st.error(f"Error initializing Google Generative AI: {str(e)}")
        return False

def get_gemini_response(prompt, context=None, temperature=0.7):
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        if context:
            full_prompt = f"""
            Context information:
            {context}

            Question: {prompt}

            Please provide a helpful, accurate response based on the context information provided.
            If the answer cannot be determined from the context, please state that clearly.
            """
        else:
            full_prompt = prompt
        response = model.generate_content(full_prompt, generation_config={"temperature": temperature})
        return response.text
    except Exception as e:
        st.error(f"Error getting response from Gemini: {str(e)}")
        return "Sorry, I couldn't generate a response at this time."

# Streamlit UI
def main():
    st.title("README.md Chatbot")

    # Initialize services
    if not st.session_state.is_initialized:
        with st.spinner("Initializing services..."):
            pinecone_init = initialize_pinecone()
            gemini_init = initialize_gemini()

            if pinecone_init and gemini_init:
                st.session_state.is_initialized = True
                st.success("Services initialized successfully!")

                # Display Pinecone connection info
                st.info(f"""
                    Connected to Pinecone index:
                    - Index name: {st.session_state.index_name}
                    - Dimension: {st.session_state.index_dimensions}
                    """)
            else:
                st.error("Failed to initialize all required services. Please check your API keys in the .env file.")

                # Show .env file template
                st.code("""
# Create a .env file in the same directory with the following content:
PINECONE_API_KEY=your_pinecone_api_key
GOOGLE_API_KEY=your_google_api_key
                    """)
                return

    # Sidebar for file upload and main actions
    with st.sidebar:
        st.header("Upload README.md")
        uploaded_file = st.file_uploader("Choose a README.md file", type="md")

        if uploaded_file:
            with st.spinner("Processing README.md..."):
                # Save uploaded file to temp location
                with tempfile.NamedTemporaryFile(delete=False, suffix=".md") as temp_file:
                    temp_file.write(uploaded_file.getvalue())
                    temp_path = temp_file.name

                # Extract text
                readme_text = extract_text_from_markdown(temp_path)
                os.unlink(temp_path)  # Delete temp file

                # Store in session state
                st.session_state.current_file_content = readme_text
                st.session_state.current_file_name = uploaded_file.name

                # Chunk and embed
                chunks = chunk_text(readme_text)
                embeddings = embed_chunks(chunks)

                # Store in Pinecone
                success = store_embeddings(chunks, embeddings, st.session_state.current_file_name)

                if success:
                    st.success(f"Successfully processed {uploaded_file.name}")
                else:
                    st.error(f"Failed to process {uploaded_file.name}")

        st.divider()
        st.header("Chat Options")
        if not st.session_state.current_file_content:
            st.info("Please upload a README.md file to start chatting")

    # Main content area
    st.header("Chat with your README.md")

    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    # Chat input
    if st.session_state.current_file_content:
        user_input = st.chat_input("Ask a question about your README.md...")

        if user_input:
            # Add user message to chat history
            st.session_state.messages.append({"role": "user", "content": user_input})
            with st.chat_message("user"):
                st.write(user_input)

            # Generate response
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    # Search for relevant context
                    similar_chunks = search_similar_chunks(
                        user_input,
                        top_k=3,
                        file_name=st.session_state.current_file_name
                    )

                    # Extract text from results
                    context = "\n\n".join([match.metadata["text"] for match in similar_chunks])

                    # Get response from Gemini
                    response = get_gemini_response(user_input, context)

                    st.write(response)

                    # Add assistant message to chat history
                    st.session_state.messages.append({"role": "assistant", "content": response})
    else:
        st.info("Please upload a README.md file to start chatting")

if __name__ == "__main__":
    main()