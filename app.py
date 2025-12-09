import streamlit as st
import json
import os
import google.generativeai as genai # CHANGED: Using the standard library
from streamlit_agraph import agraph, Node, Edge, Config

# --- Page Configuration ---
st.set_page_config(layout="wide", page_title="Career Graph Explorer")

# --- CSS for Vibe Check Styling ---
st.markdown("""
<style>
    .vibe-card {
        background-color: #262730;
        padding: 15px;
        border-radius: 10px;
        margin-bottom: 10px;
        border: 1px solid #4B4B4B;
    }
    .vibe-name {
        font-size: 1.2em;
        font-weight: bold;
        color: #FF4B4B;
    }
    .vibe-reason {
        font-size: 0.9em;
        color: #FAFAFA;
    }
    .vibe-meta {
        font-size: 0.8em;
        color: #A0A0A0;
        margin-top: 5px;
    }
</style>
""", unsafe_allow_html=True)

# --- 1. State Management ---
if 'search_term' not in st.session_state:
    st.session_state.search_term = "OpenAI"
if 'graph_data' not in st.session_state:
    st.session_state.graph_data = None
if 'history' not in st.session_state:
    st.session_state.history = []

# --- 2. Google Gemini Setup (UPDATED) ---
def get_gemini_response(query):
    """
    Uses the stable google-generativeai library.
    """
    # 1. Get API Key
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
    except Exception:
        api_key = os.environ.get("GEMINI_API_KEY")
    
    if not api_key:
        st.error("⚠️ GEMINI_API_KEY not found! Please check your Streamlit Secrets.")
        return None

    # 2. Configure the library
    genai.configure(api_key=api_key)

    # 3. Define the System Prompt
    system_instruction = """
    You are a Career Data Engine. Analyze the user's input.
    
    1. INTENT DETECTION: Determine if the input is a 'Company' (e.g., SpaceX, Google) or a 'Job Title/Skill' (e.g., Python Developer, Marketing Manager).
    
    2. DATA GENERATION:
       - If COMPANY: Return 6-8 Competitors or companies with similar engineering cultures.
       - If JOB TITLE: Return 6-8 Top Companies known for hiring this role with good reputation.
    
    3. OUTPUT FORMAT: Return ONLY valid JSON. No markdown formatting.
    Structure:
    {
        "center_node_type": "Company" or "Job",
        "center_node_label": "Corrected Name of Input",
        "connections": [
            {
                "name": "Company Name",
                "type": "Competitor" or "Hiring Company",
                "industry": "Industry Name",
                "reason": "A short, punchy 'vibe check' (max 15 words) explaining the culture or why it's a match."
            }
        ]
    }
    """

    # 4. Create Model & Generate
    # We use 'gemini-1.5-flash' which is standard. 
    # If this fails, 'gemini-pro' is a safe fallback.
    try:
        model = genai.GenerativeModel(
            model_name='gemini-flash-latest', 
            system_instruction=system_instruction,
            generation_config={"response_mime_type": "application/json"}
        )
        
        response = model.generate_content(f"Analyze this query: '{query}'")
        return json.loads(response.text)
        
    except Exception as e:
        st.error(f"AI Error: {e}")
        return None

# --- 3. UI & Logic ---

st.title("🕸️ Career Graph Explorer")
st.markdown("Enter a **Company** (to find competitors) or a **Job Title** (to find where to apply). Click nodes to explore infinitely!")

with st.sidebar:
    st.header("🔍 Search")
    user_input = st.text_input("Enter Company or Job:", value=st.session_state.search_term)
    if st.button("Explore"):
        st.session_state.search_term = user_input

# --- 4. Main Data Loop ---

current_query = st.session_state.search_term

if 'last_fetched_query' not in st.session_state:
    st.session_state.last_fetched_query = ""

data = st.session_state.graph_data

if current_query != st.session_state.last_fetched_query:
    with st.spinner(f"AI is analyzing '{current_query}'..."):
        data = get_gemini_response(current_query)
        if data:
            st.session_state.graph_data = data
            st.session_state.last_fetched_query = current_query
            if current_query not in st.session_state.history:
                st.session_state.history.append(current_query)

# --- 5. Layout ---

col_graph, col_details = st.columns([3, 1.5])

if data:
    center_label = data.get("center_node_label", current_query)
    connections = data.get("connections", [])

    nodes = []
    edges = []

    nodes.append(Node(id=center_label, label=center_label, size=40, color="#FF4B4B", shape="dot"))

    for item in connections:
        nodes.append(Node(id=item['name'], label=item['name'], size=25, color="#00C0F2", shape="dot", title=item['reason']))
        edges.append(Edge(source=center_label, target=item['name'], color="#505050", type="STRAIGHT"))

    with col_graph:
        config = Config(width=800, height=600, directed=True, physics=True, nodeHighlightBehavior=True, highlightColor="#F7A7A6", collapsible=False)
        clicked_node_id = agraph(nodes=nodes, edges=edges, config=config)

        if clicked_node_id and clicked_node_id != center_label:
            st.session_state.search_term = clicked_node_id
            st.rerun()

    with col_details:
        st.subheader("📋 Vibe Check")
        st.markdown(f"**Analysis for:** {center_label}")
        for item in connections:
            html = f"""
            <div class="vibe-card">
                <div class="vibe-name">{item['name']}</div>
                <div class="vibe-reason">{item['reason']}</div>
                <div class="vibe-meta">{item['type']} | {item['industry']}</div>
            </div>
            """
            st.markdown(html, unsafe_allow_html=True)
else:
    st.info("Waiting for input...")

with st.sidebar:
    st.divider()
    st.write("Recent Explorations:")
    for h in reversed(st.session_state.history[-5:]):
        if st.button(f"🔙 {h}", key=f"hist_{h}"):
            st.session_state.search_term = h
            st.rerun()
