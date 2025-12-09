import streamlit as st
import json
import os
import textwrap
import urllib.parse
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
        background-color: #2d2222;
        border-left: 5px solid #ff4b4b;
        padding: 15px;
        border-radius: 5px;
        color: #ffcfcf;
        font-size: 0.9em;
        margin-bottom: 20px;
        display: flex;
        align-items: center;
    }
    .cost-counter {
        font-size: 0.8em;
        color: #00FF00;
        margin-top: 10px;
    }
    /* Button Tweaks */
    .stButton button {
        width: 100%;
    }
</style>
""", unsafe_allow_html=True)

# --- 1. State Management ---
if 'mode' not in st.session_state:
    st.session_state.mode = "Discovery" 
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

    filter_text = f"""
    STRICT CONSTRAINTS:
    - Target Industry: {filters['industry']}
    - Company Size Preference: {filters['size']}
    - Work Style: {filters['style']}
    """

    if mode == "Resume Match":
        # --- PROMPT B: RESUME ALIGNMENT ---
        system_instruction = f"""
        You are a Strategic Career Agent. Analyze the user's RESUME text against constraints.
        
        {filter_text}
        
        TASK:
        1. Identify Top 5 Companies that fit this resume AND constraints.
        2. For EACH company, identify 2-3 specific SKILLS from the resume that create the match.
        
        OUTPUT JSON STRUCTURE:
        {{
            "center_node": {{
                "name": "My Career",
                "type": "Candidate",
                "mission": "Based on your resume, these are your strongest alignment targets.",
                "positive_news": "Your Top Skills: [List top 3 skills found in resume]",
                "red_flags": "Gaps/Areas to Improve: [List 1-2 potential gaps]"
            }},
            "connections": [
                {{
                    "name": "Target Company",
                    "reason": "Why it fits?",
                    "sub_connections": [
                        {{"name": "Matched Skill 1", "reason": "Relevance"}},
                        {{"name": "Matched Skill 2", "reason": "Relevance"}}
                    ]
                }}
            ]
        }}
        """
        user_prompt = f"{system_instruction}\n\nRESUME TEXT:\n{query}"

    else:
        # --- PROMPT A: DISCOVERY ---
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
        
        input_tokens = len(user_prompt) / 4
        output_tokens = len(response.text) / 4
        st.session_state.token_usage += (input_tokens + output_tokens)

        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_text)
        
    except Exception as e:
        st.error(f"AI Analysis Error: {e}")
        return None

def generate_email_draft(company, mission, user_resume=""):
    """Helper to generate a cold email using AI"""
    try:
        api_key = st.secrets["GEMINI_API_KEY"] if "GEMINI_API_KEY" in st.secrets else os.environ.get("GEMINI_API_KEY")
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-flash-latest')
        
        context = f"My Resume Summary: {user_resume[:500]}..." if user_resume else "I am a passionate professional."
        
        prompt = f"""
        Write a short, punchy (under 150 words) cold outreach email to a recruiter at {company}.
        Context on Company: {mission}
        Context on Me: {context}
        Tone: Professional, enthusiastic, but not cringey.
        Output: Just the email body.
        """
        response = model.generate_content(prompt)
        return response.text
    except:
        return "Could not generate draft. Try again."

# --- 3. Sidebar Controls ---
with st.sidebar:
    st.title("🕸️ Career Explorer")
    
    # 1. Mode Switcher
    mode = st.radio("Select Mode:", ["Discovery", "Resume Match"], horizontal=True)
    st.session_state.mode = mode

    # 2. Input Section
    if mode == "Discovery":
        st.subheader("🔍 Search")
        user_input = st.text_input("Enter Seed Company/Role:", value=st.session_state.search_term)
    else:
        st.subheader("📄 Resume Match")
        st.info("🔒 Data is analyzed transiently and not stored.")
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

    # 4. Primary Action
    if st.button("🚀 Launch Analysis", type="primary"):
        st.session_state.graph_data = None
        if mode == "Discovery":
            st.session_state.search_term = user_input
        else:
            st.session_state.resume_text = user_resume
        st.rerun()

    # 5. Clear
    if st.button("🗑️ Clear Session"):
        st.session_state.history = []
        st.session_state.graph_data = None
        st.session_state.search_term = "OpenAI"
        st.session_state.resume_text = ""
        st.session_state.token_usage = 0
        st.rerun()

    cost = (st.session_state.token_usage / 1000000) * 0.50
    st.markdown(f"<div class='cost-counter'>💰 Est. Session Cost: ${cost:.5f}</div>", unsafe_allow_html=True)

# --- 4. Main Logic ---
filters = {"industry": f_industry, "size": f_size, "style": f_style}

if st.session_state.mode == "Discovery":
    active_query = st.session_state.search_term
elif st.session_state.mode == "Resume Match":
    active_query = st.session_state.resume_text
    if not active_query:
        st.info("👈 Please paste your resume in the sidebar to begin.")
        st.stop()

# Auto-Fetch Logic
should_fetch = False
if st.session_state.graph_data is None:
    should_fetch = True
elif st.session_state.mode == "Discovery" and st.session_state.graph_data.get('center_node', {}).get('name') != active_query:
    should_fetch = True

if should_fetch:
    data = get_gemini_response(st.session_state.mode, active_query, filters)
    if data:
        st.session_state.graph_data = data
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
    st.markdown("""
    <div class="warning-box">
        <div>⚠️ <b>AI Generated Advisory:</b> Information is generated by Gemini Pro. Verify all role availability, financial health, and company details independently.</div>
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
        height=550,
        directed=False, 
        physics=True, 
        hierarchical=False,
        nodeHighlightBehavior=True,
        highlightColor="#F7A7A6",
        collapsible=False
    )

    col_main, col_right = st.columns([2.5, 1])
    
    with col_main:
        clicked_node = agraph(nodes=nodes, edges=edges, config=config)

    # --- RIGHT COLUMN: Tabs ---
    with col_right:
        # TABS: Dossier | Actions | Network
        tab_dossier, tab_actions, tab_net = st.tabs(["📂 Dossier", "⚡ Actions", "🕸️ Network"])
        
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
                        <span class="highlight-title">🚩 Red Flags</span><br>
                        {center_info['red_flags']}
                    </p>
                </div>
            """
            st.markdown(textwrap.dedent(raw_html), unsafe_allow_html=True)

        with tab_actions:
            st.subheader("Take Action")
            st.markdown("Don't just look, apply.")
            
            # 1. SMART LINKS
            company_safe = urllib.parse.quote(center_info['name'])
            st.link_button(f"💼 Jobs at {center_info['name']} (LinkedIn)", 
                           f"https://www.linkedin.com/jobs/search/?keywords={company_safe}")
            st.link_button(f"📰 News about {center_info['name']} (Google)", 
                           f"https://www.google.com/search?q={company_safe}+news&tbm=nws")
            
            st.divider()
            
            # 2. EMAIL GENERATOR
            st.write("**📧 Cold Outreach Generator**")
            if st.button("Draft Email to Recruiter"):
                with st.spinner("Writing draft..."):
                    draft = generate_email_draft(center_info['name'], center_info['mission'], st.session_state.resume_text)
                    st.text_area("Copy this:", value=draft, height=200)

        with tab_net:
            st.write("### Connections")
            for c in connections:
                st.markdown(f"**{c['name']}**")
                st.caption(f"{c['reason']}")
                st.divider()

    # --- Interaction Handler ---
    if clicked_node and clicked_node != center_info['name']:
        st.session_state.mode = "Discovery"
        st.session_state.search_term = clicked_node
        st.session_state.graph_data = None 
        st.rerun()

else:
    st.info("Waiting for input...")
