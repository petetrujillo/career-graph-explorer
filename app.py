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
    /* Card Styling */
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
    .warning-box {
        background-color: #331111;
        border: 1px solid #FF4B4B;
        padding: 10px;
        border-radius: 5px;
        color: #FF9999;
        font-size: 0.85em;
        margin-bottom: 15px;
        text-align: center;
    }
    .cost-counter {
        font-size: 0.8em;
        color: #00FF00;
        margin-top: 10px;
    }
</style>
""", unsafe_allow_html=True)

# --- 1. State Management ---
if 'mode' not in st.session_state:
    st.session_state.mode = "Discovery" # Discovery vs Resume Match
if 'search_term' not in st.session_state:
    st.session_state.search_term = "OpenAI"
if 'resume_text' not in st.session_state:
    st.session_state.resume_text = ""
if 'graph_data' not in st.session_state:
    st.session_state.graph_data = None
if 'history' not in st.session_state:
    st.session_state.history = []
if 'token_usage' not in st.session_state:
    st.session_state.token_usage = 0

# --- 2. Google Gemini Setup ---
def get_gemini_response(mode, query, filters):
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
    except Exception:
        api_key = os.environ.get("GEMINI_API_KEY")
    
    if not api_key:
        st.error("⚠️ GEMINI_API_KEY not found! Check your Streamlit Secrets.")
        return None

    genai.configure(api_key=api_key)

    # Common Filters
    filter_text = f"""
    STRICT CONSTRAINTS:
    - Target Industry: {filters['industry']}
    - Company Size Preference: {filters['size']}
    - Work Style: {filters['style']}
    """

    if mode == "Resume Match":
        # --- PROMPT B: RESUME ALIGNMENT (Company-First) ---
        system_instruction = f"""
        You are a Strategic Career Agent. Analyze the user's RESUME text against the constraints.
        
        {filter_text}
        
        TASK:
        1. Identify the Top 5 Companies that fit this resume AND the constraints.
        2. For EACH company, identify 2-3 specific SKILLS or EXPERIENCES from the resume that create the match.
        
        OUTPUT JSON STRUCTURE:
        {{
            "center_node": {{
                "name": "My Career",
                "type": "Candidate",
                "mission": "Based on your resume, these are your strongest alignment targets.",
                "positive_news": "Focus on the skills highlighted in green.",
                "red_flags": "Ensure you tailor your application to these strengths."
            }},
            "connections": [
                {{
                    "name": "Target Company Name",
                    "reason": "Why is this a good fit?",
                    "sub_connections": [
                        {{"name": "Matching Skill 1 (From Resume)", "reason": "Relevance"}},
                        {{"name": "Matching Skill 2 (From Resume)", "reason": "Relevance"}}
                    ]
                }}
            ]
        }}
        """
        user_prompt = f"{system_instruction}\n\nRESUME TEXT:\n{query}"

    else:
        # --- PROMPT A: DISCOVERY (Standard) ---
        system_instruction = f"""
        You are a Strategic Career Intelligence Engine. 
        Analyze the user's input (Company or Job Title) and return a 3-layer network graph.

        {filter_text}

        PART 1: CENTER NODE (Layer 0) - Provide 'mission', 'positive_news', 'red_flags'.
        PART 2: DIRECT CONNECTIONS (Layer 1) - Identify exactly 10 related entities matching constraints.
        PART 3: SECONDARY CONNECTIONS (Layer 2) - For EACH Layer 1 entity, identify 2 top connections.

        OUTPUT JSON STRUCTURE:
        {{
            "center_node": {{ "name": "Corrected Name", "type": "Company/Job", "mission": "...", "positive_news": "...", "red_flags": "..." }},
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
        user_prompt = f"{system_instruction}\n\nUser Input: '{query}'"

    try:
        model = genai.GenerativeModel('gemini-flash-latest')
        with st.spinner(f"🔍 Analyzing..."):
            response = model.generate_content(user_prompt)
        
        # Track usage
        input_tokens = len(user_prompt) / 4
        output_tokens = len(response.text) / 4
        st.session_state.token_usage += (input_tokens + output_tokens)

        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_text)
        
    except Exception as e:
        st.error(f"AI Analysis Error: {e}")
        return None

# --- 3. Sidebar Controls ---
with st.sidebar:
    st.title("🕸️ Career Explorer")
    
    # 1. Mode Switcher (Top of Pane)
    mode = st.radio("Select Mode:", ["Discovery", "Resume Match"], horizontal=True)
    st.session_state.mode = mode

    # 2. Input Section (Dynamic based on Mode)
    if mode == "Discovery":
        st.subheader("🔍 Search")
        user_input = st.text_input("Enter Seed Company/Role:", value=st.session_state.search_term)
        # Button logic moved below filters so one button triggers all
    else:
        st.subheader("📄 Resume Match")
        st.info("🔒 Privacy: Resume data is sent to Gemini for analysis but not stored permanently. Clear session to wipe.")
        user_resume = st.text_area("Paste Resume Text:", height=150, value=st.session_state.resume_text)

    st.divider()
    
    # 3. Hunter Filters
    st.subheader("🎯 Hunter Filters")
    f_industry = st.selectbox("Target Industry", 
        ["Any", "SaaS / Software", "Fintech", "HealthTech", "Climate Tech", "E-Commerce", "Gaming", "Crypto/Web3", "Defense/Aerospace"])
    f_size = st.selectbox("Company Size", 
        ["Any", "Early Stage (<50 employees)", "Growth Stage (50-500)", "Large Corp (500+)"])
    f_style = st.selectbox("Work Style", 
        ["Any", "Remote Friendly", "In-Office / Hybrid"])

    # 4. Primary Action Button
    if st.button("🚀 Launch Analysis", type="primary"):
        # Reset graph to force reload
        st.session_state.graph_data = None
        if mode == "Discovery":
            st.session_state.search_term = user_input
        else:
            st.session_state.resume_text = user_resume
        st.rerun()

    # 5. Clear Session
    if st.button("🗑️ Clear Session"):
        st.session_state.history = []
        st.session_state.graph_data = None
        st.session_state.search_term = "OpenAI"
        st.session_state.resume_text = ""
        st.session_state.token_usage = 0
        st.rerun()

    # Cost Tracking
    cost = (st.session_state.token_usage / 1000000) * 0.50
    st.markdown(f"<div class='cost-counter'>💰 Est. Session Cost: ${cost:.5f}</div>", unsafe_allow_html=True)

# --- 4. Main Logic ---
filters = {"industry": f_industry, "size": f_size, "style": f_style}

# Determine what query to run
if st.session_state.mode == "Discovery":
    active_query = st.session_state.search_term
elif st.session_state.mode == "Resume Match":
    active_query = st.session_state.resume_text
    if not active_query:
        st.info("👈 Please paste your resume in the sidebar to begin.")
        st.stop()

# Fetch Data if needed
# We check if graph is missing OR if the center node name doesn't match the current "context"
# For Resume mode, we just check if graph is None because the Center Name is always "My Career"
should_fetch = False
if st.session_state.graph_data is None:
    should_fetch = True
elif st.session_state.mode == "Discovery" and st.session_state.graph_data.get('center_node', {}).get('name') != active_query:
    should_fetch = True

if should_fetch:
    data = get_gemini_response(st.session_state.mode, active_query, filters)
    if data:
        st.session_state.graph_data = data
        # Only add to history in Discovery mode
        if st.session_state.mode == "Discovery":
            real_name = data['center_node']['name']
            if real_name not in st.session_state.history:
                st.session_state.history.append(real_name)
            if active_query != real_name:
                st.session_state.search_term = real_name

# --- 5. Layout Rendering ---
data = st.session_state.graph_data

if data:
    center_info = data['center_node']
    connections = data['connections']

    # --- CENTER COLUMN: Warning & Graph ---
    
    # Warning Header
    st.markdown("""
    <div class="warning-box">
        ⚠️ <b>AI Generated Content:</b> Results are generated by Google Gemini. 
        Always verify company details, role availability, and financial health independently.
    </div>
    """, unsafe_allow_html=True)

    # Build Graph
    nodes = []
    edges = []
    node_ids = set()

    # Center Node
    nodes.append(Node(
        id=center_info['name'], 
        label=center_info['name'], 
        size=45, 
        color="#FF4B4B",
        font={'color': 'white'},
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
                font={'color': 'white'},
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
                        font={'color': 'white'},
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
        width=1400,
        height=600,
        directed=False, 
        physics=True, 
        hierarchical=False,
        nodeHighlightBehavior=True,
        highlightColor="#F7A7A6",
        collapsible=False
    )

    # Render Graph (Top of Page)
    col_main, col_right = st.columns([2.5, 1])
    
    with col_main:
        clicked_node = agraph(nodes=nodes, edges=edges, config=config)

    # --- RIGHT COLUMN: Tabs ---
    with col_right:
        tab_dossier, tab_links = st.tabs(["📂 Dossier", "🔗 Links"])
        
        with tab_dossier:
            st.subheader(f"{center_info['name']}")
            raw_html = f"""
                <div class="deep-dive-card">
                    <p>
                        <span class="highlight-title">📌 Overview</span><br>
                        {center_info['mission']}
                    </p>
                    <p>
                        <span class="highlight-title">🚀 Signals</span><br>
                        {center_info['positive_news']}
                    </p>
                    <p>
                        <span class="highlight-title">🚩 Notes</span><br>
                        {center_info['red_flags']}
                    </p>
                </div>
            """
            st.markdown(textwrap.dedent(raw_html), unsafe_allow_html=True)

        with tab_links:
            st.write("### Connections")
            for c in connections:
                st.markdown(f"**{c['name']}**")
                st.caption(f"{c['reason']}")
                st.divider()

    # --- Interaction Handler ---
    # If user clicks a node (and it's not the center), we switch to Discovery Mode for that node
    if clicked_node and clicked_node != center_info['name']:
        st.session_state.mode = "Discovery" # Switch mode to explore that company
        st.session_state.search_term = clicked_node
        st.session_state.graph_data = None 
        st.rerun()

else:
    st.info("Waiting for input...")
