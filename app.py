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
    /* ADAPTIVE CARD STYLING */
    .deep-dive-card {
        background-color: var(--secondary-background-color);
        color: var(--text-color);
        padding: 15px;
        border-radius: 10px;
        border: 1px solid rgba(128, 128, 128, 0.2);
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
    /* ATTEMPT TO FORCE GRAPH BACKGROUND (for dark theme visibility) */
    iframe {
        background-color: #0e1117 !important;
    }
    /* Button Tweaks */
    .stButton button {
        width: 100%;
    }
    /* Cost Tracker (Adjusted from original) */
    .cost-tracker {
        font-size: 0.8em;
        color: #00FF00;
        margin-top: 10px;
        text-align: right;
    }
</style>
""", unsafe_allow_html=True)

# --- 1. State Management ---
if 'mode' not in st.session_state:
    st.session_state.mode = "Company Discovery" 
if 'company_search_term' not in st.session_state:
    st.session_state.company_search_term = "OpenAI"
if 'role_search_term' not in st.session_state:
    st.session_state.role_search_term = "Project Manager"
if 'graph_data' not in st.session_state:
    st.session_state.graph_data = None
if 'history' not in st.session_state:
    st.session_state.history = []
if 'token_usage' not in st.session_state:
    st.session_state.token_usage = 0
if 'session_cost' not in st.session_state:
    st.session_state.session_cost = 0.0

# --- 2. Google Gemini Setup ---
def initialize_gemini():
    """Initializes and configures the Gemini client."""
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
    except Exception:
        api_key = os.environ.get("GEMINI_API_KEY")
    
    if not api_key:
        st.error("⚠️ GEMINI_API_KEY not found! Check your Streamlit Secrets.")
        return None

    genai.configure(api_key=api_key)
    return genai.GenerativeModel('gemini-2.5-flash')

def get_gemini_response(mode, query, filters):
    """Generates content based on the selected mode and filters."""
    model = initialize_gemini()
    if not model:
        return None

    # Common model logic and prompt construction
    if mode == "Company Discovery":
        # --- PROMPT A: COMPANY DISCOVERY ---
        filter_text = f"""
        STRICT CONSTRAINTS:
        - Target Industry: {filters['industry']}
        - Company Size Preference: {filters['size']}
        - Work Style: {filters['style']}
        """
        system_instruction = f"""
        You are a Strategic Career Intelligence Engine focused on market discovery. 
        Analyze the user's input (Company or Job Title) and return a 3-layer network graph of related companies.

        {filter_text}

        PART 1: CENTER NODE (Layer 0) - Provide 'mission', 'positive_news', 'red_flags' for the input entity.
        PART 2: DIRECT CONNECTIONS (Layer 1) - Identify exactly 10 related entities (Competitors, Partners, Next-Step Companies) matching constraints.
        PART 3: SECONDARY CONNECTIONS (Layer 2) - For EACH Layer 1 entity, identify 2 top related companies or technologies.

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

    elif mode == "Role Search":
        # --- PROMPT B: ROLE SEARCH (New Logic) ---
        filter_text = f"""
        STRICT CONSTRAINTS:
        - Target Industry: {filters['industry']}
        - Preferred Role Function: {filters['function']}
        """
        system_instruction = f"""
        You are a Strategic Career Path Advisor. 
        Analyze the user's input (a Seed Job Title) and return a 3-layer network graph mapping career progression.

        {filter_text}

        PART 1: CENTER NODE (Layer 0) - The Seed Job Title ({query}). Provide 'mission', 'positive_news', 'red_flags' for this role.
        PART 2: DIRECT CONNECTIONS (Layer 1) - Identify exactly 5 distinct **alternative or next-step career paths/roles** that fit the job's core skills and constraints.
        PART 3: SECONDARY CONNECTIONS (Layer 2) - For EACH Layer 1 role, identify 2-3 specific, high-value **certifications or key skills** that would help a candidate transition into THAT specific role.

        OUTPUT JSON STRUCTURE:
        {{
            "center_node": {{ "name": "Corrected Name", "type": "Job Title", "mission": "...", "positive_news": "...", "red_flags": "..." }},
            "connections": [
                {{
                    "name": "Alternative Role Title",
                    "reason": "Why this role is an alternative path?",
                    "sub_connections": [
                        {{"name": "Certification A", "reason": "Why this cert?"}},
                        {{"name": "Certification B", "reason": "Why this cert?"}}
                    ]
                }}
            ]
        }}
        """
        user_prompt = f"{system_instruction}\n\nUser Input: '{query}'"

    else:
        return None # Should not happen

    try:
        with st.spinner(f"🔍 Analyzing {mode}..."):
            response = model.generate_content(user_prompt)
        
        # Token and Cost Tracking
        input_tokens = len(user_prompt) / 4
        output_tokens = len(response.text) / 4
        st.session_state.token_usage += (input_tokens + output_tokens)
        
        # Approximate cost calculation for Gemini Flash
        # Input: $0.0001 / 1K tokens. Output: $0.0002 / 1K tokens.
        cost = (input_tokens / 1000) * 0.0001 + (output_tokens / 1000) * 0.0002
        st.session_state.session_cost += cost
        
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_text)
        
    except Exception as e:
        st.error(f"AI Analysis Error: {e}")
        return None

def generate_email_draft(company, mission):
    """Helper to generate a cold email using AI (Kept for Company Discovery Action Tab)"""
    try:
        model = initialize_gemini()
        if not model:
            return "Could not initialize AI model."
            
        prompt = f"""
        Write a short, punchy (under 150 words) cold outreach email to a recruiter at {company}.
        Context on Company: {mission}
        Tone: Professional, enthusiastic.
        Output: Just the email body.
        """
        response = model.generate_content(prompt)
        return response.text
    except:
        return "Could not generate draft. Try again."


# --- 3. Sidebar Controls ---
with st.sidebar:
    st.title("🕸️ Career Graph Explorer")
    
    # --- TABS: Controls | About | Model Card ---
    tab_controls, tab_about, tab_model = st.tabs(["🚀 Controls", "ℹ️ About", "🧠 Model Card"])
    
    with tab_controls:
        # 1. Mode Switcher
        mode = st.radio("Select Explorer Mode:", ["Company Discovery", "Role Search"], horizontal=False)
        st.session_state.mode = mode

        st.divider()
        
        # 2. Input Section
        if mode == "Company Discovery":
            st.subheader("🔍 Seed Company/Role")
            user_input = st.text_input("Enter Company or Seed Role:", value=st.session_state.company_search_term)
        else:
            st.subheader("🎓 Seed Job Title")
            user_input = st.text_input("Enter Seed Job Title (e.g. Project Manager):", value=st.session_state.role_search_term)

        st.divider()
        
        # 3. Dynamic Filters
        st.subheader("🎯 Refine Search Filters")

        # Filters for Company Discovery
        if mode == "Company Discovery":
            f_industry = st.selectbox("Target Industry", 
                ["Any", "SaaS / Software", "Fintech", "HealthTech", "Climate Tech", "E-Commerce", "Gaming", "Crypto/Web3", "Defense/Aerospace"])
            f_size = st.selectbox("Company Size", 
                ["Any", "Early Stage (<50 employees)", "Growth Stage (50-500)", "Large Corp (500+)"])
            f_style = st.selectbox("Work Style", 
                ["Any", "Remote Friendly", "In-Office / Hybrid"])
            # Set unused filters to None/Any for consistent passing
            f_function = "Any" 
        
        # Filters for Role Search (Option B: Industry and Function)
        else: 
            f_industry = st.selectbox("Target Industry", 
                ["Any", "SaaS / Software", "Government / Public Sector", "Consulting", "Defense & Aerospace", "Financial Services", "Healthcare"])
            f_function = st.selectbox("Role Function", 
                ["Any", "Product & Strategy", "Engineering & Dev", "Risk & Compliance", "Policy & Research", "Technical Program Mgmt", "Data Science"])
            # Set unused filters to None/Any
            f_size = "Any"
            f_style = "Any"


        # 4. Primary Action
        if st.button("🚀 Launch Analysis", type="primary"):
            # Update state with new query, clear old data, and rerun
            if mode == "Company Discovery":
                st.session_state.company_search_term = user_input
            else:
                st.session_state.role_search_term = user_input
                
            st.session_state.graph_data = None
            st.session_state.mode = mode # Ensure the mode is saved before rerun
            st.rerun()

        # 5. Clear
        if st.button("🗑️ Clear Session"):
            st.session_state.history = []
            st.session_state.graph_data = None
            st.session_state.company_search_term = "OpenAI"
            st.session_state.role_search_term = "Project Manager"
            st.session_state.token_usage = 0
            st.session_state.session_cost = 0.0
            st.rerun()
            
        st.divider()
        # 6. Cost Tracker
        st.markdown(f"<div class='cost-tracker'>💰 Est. Session Cost: ${st.session_state.session_cost:.5f}</div>", unsafe_allow_html=True)
        st.caption("AI model queries cost a small amount.")

    with tab_about:
        st.subheader("About the Project")
        st.markdown("This tool visualizes career and company networks using generative AI to help you explore career paths and market intelligence.")
        st.markdown("### ☕ Support the Project")
        st.markdown(
            """
            <div style="text-align: center;">
                <a href="https://buymeacoffee.com/petetru" target="_blank">
                    <img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 45px !important;width: 162px !important;" >
                </a>
            </div>
            """,
            unsafe_allow_html=True
        )

    with tab_model:
        st.subheader("🧠 Model Card")
        st.caption("Transparency on how this tool works.")
        
        st.markdown("""
        **Project:** Career Graph Explorer  
        **Model Engine:** Google Gemini 2.5 Flash  
        **Purpose:** To map company ecosystems and career progressions.

        #### 🎯 Intended Use
        * **Company Discovery:** Maps a seed company/role to competitors, partners, and related entities (Layer 1 & 2).
        * **Role Search:** Maps a seed job title to alternative roles (Layer 1) and required certifications/skills (Layer 2).

        #### ⚙️ How It Works
        The tool uses distinct prompting strategies for each mode:
        | Mode | **Center Node (L0)** | **Connections (L1)** | **Sub-Connections (L2)** |
        | :--- | :--- | :--- | :--- |
        | **Company Discovery** | Seed Company/Role | Related Companies | Secondary Company/Tech |
        | **Role Search** | Seed Job Title | Alternative/Next-Step Roles | Certifications/Key Skills |

        #### ⚠️ Limitations
        * **Hallucination Risk:** AI may occasionally suggest outdated information.
        * **Knowledge Cutoff:** Suggestions are based on the model's training data cutoff.
        * **Advisory:** Always verify role availability, financial requirements (for certs), and company details independently.
        """)


# --- 4. Main Logic ---
filters = {
    "industry": f_industry, 
    "size": f_size, 
    "style": f_style, 
    "function": f_function # Used only for Role Search
}

active_mode = st.session_state.mode

if active_mode == "Company Discovery":
    active_query = st.session_state.company_search_term
elif active_mode == "Role Search":
    active_query = st.session_state.role_search_term
    
if not active_query:
    st.info("👈 Please enter an input in the sidebar to begin.")
    st.stop()


# Auto-Fetch Logic - Check if we need to run the model
should_fetch = False
if st.session_state.graph_data is None:
    should_fetch = True
elif st.session_state.graph_data.get('mode') != active_mode:
    should_fetch = True
elif st.session_state.graph_data.get('center_node', {}).get('name') != active_query:
    should_fetch = True
# Note: Filters change will require the user to hit the button manually, as is standard practice.

if should_fetch:
    data = get_gemini_response(active_mode, active_query, filters)
    if data:
        data['mode'] = active_mode # Save the mode to state data for comparison
        st.session_state.graph_data = data
        
        # EXTRACT THE REAL NAME FROM AI RESPONSE
        real_name = data['center_node']['name']
        
        # 1. Handle Company Discovery Updates
        if active_mode == "Company Discovery":
            if real_name not in st.session_state.history:
                st.session_state.history.append(real_name)
            if active_query != real_name:
                st.session_state.company_search_term = real_name
        
        # 2. Handle Role Search Updates (THIS WAS MISSING)
        elif active_mode == "Role Search":
            if active_query != real_name:
                st.session_state.role_search_term = real_name

        st.rerun()

# --- 5. Layout Rendering ---
data = st.session_state.graph_data

if data:
    center_info = data['center_node']
    connections = data['connections']
    
    # --- CENTER COLUMN: Warning & Graph ---
    st.markdown("""
    <div class="warning-box">
        <div>⚠️ <b>AI Generated Advisory:</b> Information is generated by Gemini 2.5 Flash. Verify all details independently.</div>
    </div>
    """, unsafe_allow_html=True)

    # Build Graph
    nodes = []
    edges = []
    node_ids = set()
    
    # Define High-Contrast Font
    high_contrast_font = {
        'color': 'white',
        'strokeWidth': 4,        
        'strokeColor': 'black'  
    }

    # Center Node (Layer 0)
    center_color = "#FF4B4B" if active_mode == "Company Discovery" else "#B19CD9"
    center_shape = "dot" if active_mode == "Company Discovery" else "square"
    
    nodes.append(Node(
        id=center_info['name'], 
        label=center_info['name'], 
        size=45, 
        color=center_color,
        font=high_contrast_font,
        shape=center_shape,
        url="javascript:void(0);"
    ))
    node_ids.add(center_info['name'])

    for item in connections:
        # Layer 1: Companies (Discovery) or Alternative Roles (Role Search)
        l1_color = "#00C0F2"
        l1_shape = "dot"
        if active_mode == "Role Search":
            l1_color = "#FF4B4B"
            l1_shape = "diamond"
            
        if item['name'] not in node_ids:
            nodes.append(Node(
                id=item['name'], 
                label=item['name'], 
                size=30, 
                color=l1_color,
                font=high_contrast_font,
                title=item['reason'],
                shape=l1_shape,
                url="javascript:void(0);"
            ))
            node_ids.add(item['name'])
        
        edges.append(Edge(
            source=center_info['name'], 
            target=item['name'], 
            color="#808080",
            width=2
        ))

        # Layer 2: Secondary Connections (Discovery) or Certifications (Role Search)
        if 'sub_connections' in item:
            for sub in item['sub_connections']:
                l2_color = "#1DB954" # Green for Company Discovery secondary connections
                l2_shape = "dot"
                l2_title = f"Connected to {item['name']}"
                
                if active_mode == "Role Search":
                    l2_color = "#00C0F2" # Blue for Certifications
                    l2_shape = "star"
                    l2_title = f"Cert for {item['name']}: {sub['reason']}"

                if sub['name'] not in node_ids:
                    nodes.append(Node(
                        id=sub['name'], 
                        label=sub['name'], 
                        size=20, 
                        color=l2_color, 
                        font=high_contrast_font,
                        title=l2_title,
                        shape=l2_shape,
                        url="javascript:void(0);"
                    ))
                    node_ids.add(sub['name'])
                
                edges.append(Edge(
                    source=item['name'], 
                    target=sub['name'], 
                    color="#404040", 
                    width=1,
                    dashes=True if active_mode == "Role Search" else False
                ))

    config = Config(
        width=1400,
        height=550,
        directed=False if active_mode == "Company Discovery" else True, # Role search can be seen as directed
        physics=True, 
        hierarchical=False,
        nodeHighlightBehavior=True,
        highlightColor="#F7A7A6",
        collapsible=False,
        backgroundColor="#0e1117"
    )

    col_main, col_right = st.columns([2.5, 1])
    
    with col_main:
        clicked_node = agraph(nodes=nodes, edges=edges, config=config)

    # --- RIGHT COLUMN: Tabs ---
    with col_right:
        # TABS: Dossier | Actions | Network
        tab_dossier, tab_actions, tab_net = st.tabs(["📂 Dossier", "⚡ Actions", "🕸️ Network"])
        
        # Determine the selected node for Dossier/Actions
        selected_node_name = clicked_node if clicked_node else center_info['name']
        
        # --- Dossier Tab Logic ---
        with tab_dossier:
            st.subheader(f"Details: {selected_node_name}")
            
            # Find the details for the selected node
            display_mission = center_info['mission']
            display_positive = center_info['positive_news']
            display_redflags = center_info['red_flags']
            
            if selected_node_name != center_info['name']:
                found = False
                for c in connections:
                    if c['name'] == selected_node_name:
                        display_mission = c['reason']
                        display_positive = "Target Role" if active_mode == "Role Search" else "Key Relatability"
                        display_redflags = ""
                        found = True
                        break
                    for sub in c.get('sub_connections', []):
                        if sub['name'] == selected_node_name:
                            display_mission = sub['reason']
                            display_positive = f"Required for: {c['name']}"
                            display_redflags = ""
                            found = True
                            break
                if not found:
                    display_mission = "Node details not found."
            
            # Render Dossier Card
            raw_html = f"""
                <div class="deep-dive-card">
                    <p>
                        <span class="highlight-title">📌 Overview</span><br>
                        {display_mission}
                    </p>
                    <p>
                        <span class="highlight-title">🚀 Signals / Focus</span><br>
                        {display_positive}
                    </p>
                    <p>
                        <span class="highlight-title">🚩 Caveat / Gap</span><br>
                        {display_redflags}
                    </p>
                </div>
            """
            st.markdown(textwrap.dedent(raw_html), unsafe_allow_html=True)


        # --- Actions Tab Logic ---
        with tab_actions:
            st.subheader("Take Action")
            st.markdown("Leverage this analysis.")
            
            # 1. SMART LINKS
            company_or_role_safe = urllib.parse.quote(selected_node_name)
            
            if active_mode == "Company Discovery":
                st.link_button(f"💼 Jobs at {selected_node_name} (LinkedIn)", 
                               f"https://www.linkedin.com/jobs/search/?keywords={company_or_role_safe}")
                st.link_button(f"📰 News about {selected_node_name} (Google)", 
                               f"https://www.google.com/search?q={company_or_role_safe}+news&tbm=nws")
            else: # Role Search actions
                st.link_button(f"💼 Search Jobs for {selected_node_name}", 
                               f"https://www.linkedin.com/jobs/search/?keywords={company_or_role_safe}")
                st.link_button(f"🔎 Research Requirements (Google)", 
                               f"https://www.google.com/search?q={company_or_role_safe}+certification+requirements")

            st.divider()
            
            # 2. EMAIL GENERATOR (Only for Company Discovery - Center Node)
            if active_mode == "Company Discovery" and selected_node_name == center_info['name']:
                st.write("**📧 Cold Outreach Generator**")
                if st.button("Draft Email to Recruiter"):
                    with st.spinner("Writing draft..."):
                        draft = generate_email_draft(center_info['name'], center_info['mission'])
                        st.text_area("Copy this:", value=draft, height=200)


        # --- Network Tab Logic ---
        with tab_net:
            st.write("### Connections")
            for c in connections:
                st.markdown(f"**{c['name']}**")
                st.caption(f"{c['reason']}")
                
                if 'sub_connections' in c:
                    sub_list = ", ".join([sub['name'] for sub in c['sub_connections']])
                    st.caption(f"Sub-Connections: {sub_list}")
                st.divider()

    # --- Interaction Handler (Only for Company Discovery Mode) ---
    if clicked_node and clicked_node != center_info['name'] and active_mode == "Company Discovery":
        st.session_state.mode = "Company Discovery"
        st.session_state.company_search_term = clicked_node
        st.session_state.graph_data = None 
        st.rerun()

else:
    # Landing state for the main page when no graph data exists
    st.markdown("""
    <div style="text-align: center; padding: 50px;">
        <h1>🕸️ Welcome to the Career Graph Explorer</h1>
        <p>Select a mode and enter your search term in the sidebar to begin mapping career paths or company ecosystems.</p>
        <p style="font-size: 0.9em; color: gray;">Use **Company Discovery** for market intelligence (Layer 0->Company->Company) or **Role Search** for career strategy (Layer 0->Role->Cert).</p>
    </div>
    """, unsafe_allow_html=True)
