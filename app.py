import streamlit as st
import json
import os
import google.generativeai as genai
from streamlit_agraph import agraph, Node, Edge, Config

# --- Page Configuration ---
st.set_page_config(layout="wide", page_title="Career Graph Explorer")

# --- CSS for Vibe Check Styling ---
st.markdown("""
<style>
    .deep-dive-card {
        background-color: #262730;
        padding: 20px;
        border-radius: 10px;
        margin-bottom: 15px;
        border: 1px solid #4B4B4B;
    }
    .metric-header {
        font-size: 1.0em;
        font-weight: bold;
        color: #FF4B4B;
        margin-top: 10px;
    }
    .metric-content {
        font-size: 0.9em;
        color: #FAFAFA;
        margin-bottom: 10px;
    }
    .connection-tag {
        display: inline-block;
        background-color: #0E1117;
        border: 1px solid #FF4B4B;
        padding: 5px 10px;
        border-radius: 15px;
        font-size: 0.8em;
        margin: 2px;
    }
</style>
""", unsafe_allow_html=True)

# --- 1. State Management ---
if 'search_term' not in st.session_state:
    st.session_state.search_term = "OpenAI" # Default start
if 'graph_data' not in st.session_state:
    st.session_state.graph_data = None
if 'history' not in st.session_state:
    st.session_state.history = []

# --- 2. Google Gemini Setup ---
def get_gemini_response(query):
    # 1. Get API Key
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
    except Exception:
        api_key = os.environ.get("GEMINI_API_KEY")
    
    if not api_key:
        st.error("⚠️ GEMINI_API_KEY not found! Please check your Streamlit Secrets.")
        return None

    # 2. Configure
    genai.configure(api_key=api_key)

    # 3. Enhanced System Prompt (Your Specific Requirements)
    system_instruction = """
    You are a Strategic Career Intelligence Engine. 
    Analyze the user's input (Company or Job Title) and return a STRICT JSON object.

    PART 1: CENTER NODE ANALYSIS (The Deep Dive)
    For the input entity, provide:
    1. "mission": Brief, neutral overview of mission/product.
    2. "positive_news": Major positive news from last 6-12 months (e.g. launches, earnings).
    3. "red_flags": Recent red flags or neutral warnings (e.g. layoffs, restructuring).
    
    PART 2: CONNECTIONS (The Graph)
    Identify 6-8 related entities:
    - If input is Company -> Return Competitors.
    - If input is Job -> Return Top Hiring Companies.
    
    PART 3: JSON STRUCTURE
    Return ONLY raw JSON. No markdown.
    {
        "center_node": {
            "name": "Corrected Name",
            "type": "Company" or "Job",
            "mission": "...",
            "positive_news": "...",
            "red_flags": "..."
        },
        "connections": [
            {
                "name": "Related Company Name",
                "reason": "Why is this connected? (Short context)",
                "type": "Competitor" or "Hiring"
            }
        ]
    }
    """

    try:
        model = genai.GenerativeModel('gemini-flash-latest')
        full_prompt = f"{system_instruction}\n\nUser Input: '{query}'"
        
        with st.spinner(f"🔍 AI is digging into {query}..."):
            response = model.generate_content(full_prompt)
        
        # Clean response string (Gemini sometimes adds ```json markers)
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_text)
        
    except Exception as e:
        st.error(f"AI Analysis Error: {e}")
        return None

# --- 3. Sidebar Controls ---
with st.sidebar:
    st.header("🕸️ Career Explorer")
    # Search Input
    user_input = st.text_input("Search Company/Role:", value=st.session_state.search_term)
    if st.button("New Search"):
        st.session_state.search_term = user_input
        st.rerun()

    st.divider()
    st.write("Recent Path:")
    # Reverse history to show newest first
    for i, h in enumerate(reversed(st.session_state.history[-5:])):
        if st.button(f"🔙 {h}", key=f"hist_{i}"):
            st.session_state.search_term = h
            st.rerun()

# --- 4. Main Data Logic ---
current_query = st.session_state.search_term

# Trigger fetch if query changed OR if data is missing
if st.session_state.graph_data is None or \
   st.session_state.graph_data.get('center_node', {}).get('name') != current_query:
    
    data = get_gemini_response(current_query)
    if data:
        st.session_state.graph_data = data
        # Add to history if unique
        real_name = data['center_node']['name']
        if real_name not in st.session_state.history:
            st.session_state.history.append(real_name)
        # Update search term to match the cleaned name
        if current_query != real_name:
            st.session_state.search_term = real_name

# --- 5. Layout Rendering ---
data = st.session_state.graph_data

if data:
    col_graph, col_details = st.columns([2.5, 1.5])
    
    center_info = data['center_node']
    connections = data['connections']

# --- RIGHT COLUMN: The "Deep Dive" Side Pane ---
    with col_details:
        st.subheader(f"🏢 {center_info['name']}")
        
        # FIX: We remove indentation inside the string to prevent Markdown from making it a code block
        html = f"""
<div class="deep-dive-card">
    <div class="metric-header">📌 Mission / Overview</div>
    <div class="metric-content">{center_info['mission']}</div>
    
    <div class="metric-header">🚀 Positive Signals</div>
    <div class="metric-content">{center_info['positive_news']}</div>
    
    <div class="metric-header">🚩 Red Flags / Awareness</div>
    <div class="metric-content">{center_info['red_flags']}</div>
</div>
"""
        st.markdown(html, unsafe_allow_html=True)
        
        st.write("### 🔗 Connections Found:")
        for c in connections:
             # Using a cleaner bullet point format for the connections
            st.markdown(f"- **{c['name']}**: {c['reason']}")

    # --- LEFT COLUMN: The Graph ---
    with col_graph:
        nodes = []
        edges = []

        # 1. Center Node
        nodes.append(Node(
            id=center_info['name'], 
            label=center_info['name'], 
            size=45, 
            color="#FF4B4B",
            font={'color': 'white'}
        ))

        # 2. Connection Nodes
        for item in connections:
            nodes.append(Node(
                id=item['name'], 
                label=item['name'], 
                size=25, 
                color="#00C0F2",
                title=item['reason']
            ))
            edges.append(Edge(
                source=center_info['name'], 
                target=item['name'], 
                color="#505050",
            ))

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

        # RENDER GRAPH & CAPTURE CLICK
        clicked_node = agraph(nodes=nodes, edges=edges, config=config)

        # --- THE INFINITE DRILL LOGIC ---
        # If a node is clicked AND it's not the one we are already looking at:
        if clicked_node and clicked_node != center_info['name']:
            st.session_state.search_term = clicked_node
            st.rerun() # Force immediate reload with new center
            
else:
    st.info("Waiting for data...")
