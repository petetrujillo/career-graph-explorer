import streamlit as st
import json
import os
import textwrap
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
        color: #FAFAFA;
    }
    .deep-dive-card p {
        margin-bottom: 15px;
        line-height: 1.5;
    }
    .highlight-title {
        color: #FF4B4B;
        font-weight: bold;
        font-size: 1.05em;
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

# --- 2. Google Gemini Setup ---
def get_gemini_response(query):
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
    except Exception:
        api_key = os.environ.get("GEMINI_API_KEY")
    
    if not api_key:
        st.error("⚠️ GEMINI_API_KEY not found! Check your Streamlit Secrets.")
        return None

    genai.configure(api_key=api_key)

    system_instruction = """
    You are a Strategic Career Intelligence Engine. 
    Analyze the user's input (Company or Job Title) and return a STRICT JSON object.

    PART 1: CENTER NODE ANALYSIS (The Deep Dive)
    For the input entity, provide:
    1. "mission": Brief, neutral overview of mission/product.
    2. "positive_news": Major positive news from last 6-12 months.
    3. "red_flags": Recent red flags or neutral warnings.
    
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
        model = genai.GenerativeModel('gemini-pro')
        full_prompt = f"{system_instruction}\n\nUser Input: '{query}'"
        
        with st.spinner(f"🔍 AI is digging into {query}..."):
            response = model.generate_content(full_prompt)
        
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_text)
        
    except Exception as e:
        st.error(f"AI Analysis Error: {e}")
        return None

# --- 3. Sidebar Controls ---
with st.sidebar:
    st.header("🕸️ Career Explorer")
    user_input = st.text_input("Search Company/Role:", value=st.session_state.search_term)
    if st.button("New Search"):
        st.session_state.search_term = user_input
        st.rerun()

    st.divider()
    st.write("Recent Path:")
    for i, h in enumerate(reversed(st.session_state.history[-5:])):
        if st.button(f"🔙 {h}", key=f"hist_{i}"):
            st.session_state.search_term = h
            st.rerun()

# --- 4. Main Data Logic ---
current_query = st.session_state.search_term

if st.session_state.graph_data is None or \
   st.session_state.graph_data.get('center_node', {}).get('name') != current_query:
    
    data = get_gemini_response(current_query)
    if data:
        st.session_state.graph_data = data
        real_name = data['center_node']['name']
        if real_name not in st.session_state.history:
            st.session_state.history.append(real_name)
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
        
        # --- SIMPLIFIED HTML STRUCTURE ---
        # Using simple <p> tags and <br> for breaks. No complex nesting.
        raw_html = f"""
            <div class="deep-dive-card">
                <p>
                    <span class="highlight-title">📌 Mission / Overview</span><br>
                    {center_info['mission']}
                </p>
                <p>
                    <span class="highlight-title">🚀 Positive Signals</span><br>
                    {center_info['positive_news']}
                </p>
                <p>
                    <span class="highlight-title">🚩 Red Flags / Awareness</span><br>
                    {center_info['red_flags']}
                </p>
            </div>
        """
        st.markdown(textwrap.dedent(raw_html), unsafe_allow_html=True)
        
        st.write("### 🔗 Connections Found:")
        for c in connections:
            st.markdown(f"- **{c['name']}**: {c['reason']}")

    # --- LEFT COLUMN: The Graph ---
    with col_graph:
        nodes = []
        edges = []

        # Center Node
        nodes.append(Node(
            id=center_info['name'], 
            label=center_info['name'], 
            size=45, 
            color="#FF4B4B",
            font={'color': 'white'}
        ))

        # Connection Nodes
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

        clicked_node = agraph(nodes=nodes, edges=edges, config=config)

        if clicked_node and clicked_node != center_info['name']:
            st.session_state.search_term = clicked_node
            st.rerun()
            
else:
    st.info("Waiting for data...")
