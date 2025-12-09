import streamlit as st
import json
import os
import textwrap
import google.generativeai as genai
from streamlit_agraph import agraph, Node, Edge, Config

# --- Page Configuration ---
st.set_page_config(layout="wide", page_title="Career Graph Explorer")

# --- CSS for Styling ---
st.markdown("""
<style>
    /* Compact Card Styling */
    .deep-dive-card {
        background-color: #262730;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #4B4B4B;
        color: #FAFAFA;
        height: 100%;
    }
    .deep-dive-card p {
        margin-bottom: 10px;
        line-height: 1.4;
        font-size: 0.95em;
    }
    .highlight-title {
        color: #FF4B4B;
        font-weight: bold;
        font-size: 1.0em;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .cost-counter {
        font-size: 0.8em;
        color: #00FF00;
        margin-top: 10px;
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
if 'token_usage' not in st.session_state:
    st.session_state.token_usage = 0

# --- 2. Google Gemini Setup ---
def get_gemini_response(query, filters):
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
    except Exception:
        api_key = os.environ.get("GEMINI_API_KEY")
    
    if not api_key:
        st.error("⚠️ GEMINI_API_KEY not found! Check your Streamlit Secrets.")
        return None

    genai.configure(api_key=api_key)

    filter_text = f"""
    STRICT CONSTRAINTS (The User is looking for a job):
    - Target Industry: {filters['industry']}
    - Company Size Preference: {filters['size']}
    - Work Style: {filters['style']}
    
    IMPORTANT: The 'Related Entities' and 'Sub-connections' MUST attempt to match these constraints.
    """

    system_instruction = f"""
    You are a Strategic Career Intelligence Engine. 
    Analyze the user's input (Company or Job Title) and return a STRICT JSON object representing a 3-layer network graph.

    {filter_text}

    PART 1: CENTER NODE (Layer 0)
    Provide 'mission', 'positive_news', and 'red_flags'.

    PART 2: DIRECT CONNECTIONS (Layer 1)
    Identify exactly 10 related entities matching constraints.
    
    PART 3: SECONDARY CONNECTIONS (Layer 2)
    For EACH of the 10 Layer 1 entities, identify 2 of THEIR top connections.

    PART 4: JSON STRUCTURE
    Return ONLY raw JSON. No markdown.
    {{
        "center_node": {{
            "name": "Corrected Name",
            "type": "Company" or "Job",
            "mission": "...",
            "positive_news": "...",
            "red_flags": "..."
        }},
        "connections": [
            {{
                "name": "Layer 1 Company",
                "reason": "Why related?",
                "sub_connections": [
                    {{"name": "Layer 2 Company A", "reason": "Reason"}},
                    {{"name": "Layer 2 Company B", "reason": "Reason"}}
                ]
            }}
        ]
    }}
    """

    try:
        model = genai.GenerativeModel('gemini-latest-flash')
        full_prompt = f"{system_instruction}\n\nUser Input: '{query}'"
        
        with st.spinner(f"🔍 Hunting for {filters['size']} companies in {filters['industry']}..."):
            response = model.generate_content(full_prompt)
        
        input_tokens = len(full_prompt) / 4
        output_tokens = len(response.text) / 4
        st.session_state.token_usage += (input_tokens + output_tokens)

        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_text)
        
    except Exception as e:
        st.error(f"AI Analysis Error: {e}")
        return None

# --- 3. Sidebar Controls ---
with st.sidebar:
    st.header("🎯 Hunter Filters")
    
    f_industry = st.selectbox("Target Industry", 
        ["Any", "SaaS / Software", "Fintech", "HealthTech", "Climate Tech", "E-Commerce", "Gaming", "Crypto/Web3", "Defense/Aerospace"])
    
    f_size = st.selectbox("Company Size", 
        ["Any", "Early Stage (<50 employees)", "Growth Stage (50-500)", "Large Corp (500+)"])
    
    f_style = st.selectbox("Work Style", 
        ["Any", "Remote Friendly", "In-Office / Hybrid"])

    st.divider()
    st.header("🔍 Search")
    user_input = st.text_input("Enter Seed Company/Role:", value=st.session_state.search_term)
    
    if st.button("Explore"):
        st.session_state.search_term = user_input
        st.session_state.graph_data = None 
        st.rerun()

    cost = (st.session_state.token_usage / 1000000) * 0.50
    st.markdown(f"<div class='cost-counter'>💰 Est. Session Cost: ${cost:.5f}</div>", unsafe_allow_html=True)

    st.divider()
    st.write("Recent Path:")
    for i, h in enumerate(reversed(st.session_state.history[-5:])):
        if st.button(f"🔙 {h}", key=f"hist_{i}"):
            st.session_state.search_term = h
            st.rerun()

# --- 4. Main Data Logic ---
current_query = st.session_state.search_term
filters = {"industry": f_industry, "size": f_size, "style": f_style}

if st.session_state.graph_data is None or \
   st.session_state.graph_data.get('center_node', {}).get('name') != current_query:
    
    data = get_gemini_response(current_query, filters)
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
    center_info = data['center_node']
    connections = data['connections']

    # --- SECTION A: The Network Graph (Full Width / Above Fold) ---
    nodes = []
    edges = []
    node_ids = set()

    # 1. Center Node
    nodes.append(Node(
        id=center_info['name'], 
        label=center_info['name'], 
        size=45, 
        color="#FF4B4B",
        font={'color': 'white'}, # FIX: White Text
        url="javascript:void(0);"
    ))
    node_ids.add(center_info['name'])

    for item in connections:
        # Layer 1
        if item['name'] not in node_ids:
            nodes.append(Node(
                id=item['name'], 
                label=item['name'], 
                size=25, 
                color="#00C0F2",
                font={'color': 'white'}, # FIX: White Text
                title=item['reason'],
                url="javascript:void(0);"
            ))
            node_ids.add(item['name'])
        
        edges.append(Edge(
            source=center_info['name'], 
            target=item['name'], 
            color="#808080",
            width=2
        ))

        # Layer 2
        if 'sub_connections' in item:
            for sub in item['sub_connections']:
                if sub['name'] not in node_ids:
                    nodes.append(Node(
                        id=sub['name'], 
                        label=sub['name'], 
                        size=15, 
                        color="#1DB954", 
                        font={'color': 'white'}, # FIX: White Text
                        title=f"Connected to {item['name']}",
                        url="javascript:void(0);"
                    ))
                    node_ids.add(sub['name'])
                
                edges.append(Edge(
                    source=item['name'], 
                    target=sub['name'], 
                    color="#404040", 
                    width=1
                ))

    config = Config(
        width=1200, # Wider to fill container
        height=600,
        directed=False, 
        physics=True, 
        hierarchical=False,
        nodeHighlightBehavior=True,
        highlightColor="#F7A7A6",
        collapsible=False
    )

    # Render Graph (Top of Page)
    clicked_node = agraph(nodes=nodes, edges=edges, config=config)

    # --- SECTION B: Deep Dive & Connections (Below Graph) ---
    col_deep, col_conn = st.columns([1, 1])

    with col_deep:
        st.subheader(f"🏢 {center_info['name']} Dossier")
        raw_html = f"""
            <div class="deep-dive-card">
                <p>
                    <span class="highlight-title">📌 Mission</span><br>
                    {center_info['mission']}
                </p>
                <p>
                    <span class="highlight-title">🚀 Positive Signals</span><br>
                    {center_info['positive_news']}
                </p>
                <p>
                    <span class="highlight-title">🚩 Red Flags</span><br>
                    {center_info['red_flags']}
                </p>
            </div>
        """
        st.markdown(textwrap.dedent(raw_html), unsafe_allow_html=True)

    with col_conn:
        st.subheader("🔗 Top Connections Analysis")
        # Creating a list view for connections
        for c in connections[:8]: # Limit length to fit nicely
            st.markdown(f"**{c['name']}**")
            st.caption(f"Reason: {c['reason']}")
            st.divider()

    # --- Interaction Handler ---
    if clicked_node and clicked_node != center_info['name']:
        st.session_state.search_term = clicked_node
        st.session_state.graph_data = None 
        st.rerun()

else:
    st.info("Waiting for data...")
