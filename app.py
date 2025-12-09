import streamlit as st
import json
import os
from google import genai
from google.genai import types
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
# Initialize session state for the search term and data caching
if 'search_term' not in st.session_state:
    st.session_state.search_term = "OpenAI" # Default start
if 'graph_data' not in st.session_state:
    st.session_state.graph_data = None
if 'history' not in st.session_state:
    st.session_state.history = []

# --- 2. Google Gemini Setup ---
def get_gemini_client():
    try:
        # Try getting from Streamlit secrets (for HF Spaces/Local)
        api_key = st.secrets["GEMINI_API_KEY"]
    except Exception:
        # Fallback to os.environ for other container setups
        api_key = os.environ.get("GEMINI_API_KEY")
    
    if not api_key:
        st.error("⚠️ GEMINI_API_KEY not found! Please set it in Hugging Face Space Secrets.")
        return None
    return genai.Client(api_key=api_key)

def fetch_career_connections(query):
    """
    Uses Gemini to determine if query is Company or Job, 
    and returns connected entities with 'vibe check' data.
    """
    client = get_gemini_client()
    if not client:
        return None

    # System prompt to enforce strict JSON structure
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

    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=f"Analyze this query: '{query}'",
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json"
            )
        )
        return json.loads(response.text)
    except Exception as e:
        st.error(f"AI Error: {e}")
        return None

# --- 3. UI & Logic ---

# Title area
st.title("🕸️ Career Graph Explorer")
st.markdown("Enter a **Company** (to find competitors) or a **Job Title** (to find where to apply). Click nodes to explore infinitely!")

# Sidebar for controls and Vibe Check
with st.sidebar:
    st.header("🔍 Search")
    
    # Search Input
    # We use a temporary key to avoid conflict with the session state used for driving the graph
    user_input = st.text_input("Enter Company or Job:", value=st.session_state.search_term)
    
    if st.button("Explore"):
        st.session_state.search_term = user_input
        # Force reload by clearing previous data logic if needed, 
        # but the main loop handles data fetching based on search_term change.

# --- 4. Main Data Loop ---

# Check if we need to fetch new data (Basic caching mechanism could be added here, 
# but for the 'infinite' feel, we fetch when the search term changes essentially)
current_query = st.session_state.search_term

# We will store the last fetched query to avoid re-fetching on simple UI interactions
if 'last_fetched_query' not in st.session_state:
    st.session_state.last_fetched_query = ""

data = st.session_state.graph_data

# Fetch data if query changed
if current_query != st.session_state.last_fetched_query:
    with st.spinner(f"AI is analyzing '{current_query}'..."):
        data = fetch_career_connections(current_query)
        if data:
            st.session_state.graph_data = data
            st.session_state.last_fetched_query = current_query
            # Add to history if unique
            if current_query not in st.session_state.history:
                st.session_state.history.append(current_query)

# --- 5. Layout: Graph vs Vibe Check ---

col_graph, col_details = st.columns([3, 1.5])

if data:
    center_label = data.get("center_node_label", current_query)
    connections = data.get("connections", [])

    # -- Build Graph Nodes & Edges --
    nodes = []
    edges = []

    # 1. Center Node
    nodes.append(Node(
        id=center_label, 
        label=center_label, 
        size=40, 
        color="#FF4B4B", # Red for center
        shape="dot"
    ))

    # 2. Connection Nodes
    for item in connections:
        nodes.append(Node(
            id=item['name'], 
            label=item['name'], 
            size=25, 
            color="#00C0F2", # Blue for recommendations
            shape="dot",
            title=item['reason'] # Tooltip
        ))
        edges.append(Edge(
            source=center_label, 
            target=item['name'], 
            color="#505050",
            type="STRAIGHT"
        ))

    # -- Render Graph in Left Column --
    with col_graph:
        config = Config(
            width=800,
            height=600,
            directed=True, 
            physics=True, 
            hierarchical=False,
            nodeHighlightBehavior=True,
            highlightColor="#F7A7A6",
            collapsible=False
        )
        
        # KEY INTERACTIVITY: agraph returns the ID of the clicked node
        clicked_node_id = agraph(nodes=nodes, edges=edges, config=config)

        # Logic: If user clicks a node that isn't the current center, update state & rerun
        if clicked_node_id and clicked_node_id != center_label:
            st.session_state.search_term = clicked_node_id
            st.rerun()

    # -- Render Vibe Check in Right Column --
    with col_details:
        st.subheader("📋 Vibe Check Details")
        st.markdown(f"**Analysis for:** {center_label}")
        
        for item in connections:
            html = f"""
            <div class="vibe-card">
                <div class="vibe-name">{item['name']}</div>
                <div class="vibe-reason">{item['reason']}</div>
                <div class="vibe-meta">Type: {item['type']} | Industry: {item['industry']}</div>
            </div>
            """
            st.markdown(html, unsafe_allow_html=True)

else:
    st.info("Waiting for input...")

# --- History ---
with st.sidebar:
    st.divider()
    st.write("Recent Explorations:")
    for h in reversed(st.session_state.history[-5:]):
        if st.button(f"🔙 {h}", key=f"hist_{h}"):
            st.session_state.search_term = h
            st.rerun()
