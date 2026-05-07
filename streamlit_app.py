import streamlit as st
import os
from supabase import create_client, Client
from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import tool
from langchain_community.tools.tavily_search import TavilySearchResults
from pypdf import PdfReader

# =================================================================
# 1. DATABASE CONNECTION
# =================================================================
def init_db():
    try:
        return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except:
        return None

supabase = init_db()

def get_user(email):
    if not supabase: return None
    try:
        r = supabase.table("profiles").select("*").eq("email", email).execute()
        return r.data[0] if r.data else None
    except: return None

def update_bal(email, val):
    if supabase:
        supabase.table("profiles").update({"balance": float(val)}).eq("email", email).execute()

# =================================================================
# 2. LOGIN & UI SETUP
# =================================================================
st.set_page_config(page_title="Calvin Pro Business", layout="wide")

if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user' not in st.session_state: st.session_state.user = ""
if 'bal' not in st.session_state: st.session_state.bal = 0.0

if not st.session_state.logged_in:
    st.title("🔐 Calvin Pro - Business Engine")
    t1, t2 = st.tabs(["Login", "Registrierung"])
    with t1:
        with st.form("l"):
            u = st.text_input("E-Mail").lower().strip()
            p = st.text_input("Passwort", type="password")
            if st.form_submit_button("Anmelden", use_container_width=True):
                data = get_user(u)
                if data and str(data["password"]) == p:
                    st.session_state.logged_in, st.session_state.user = True, u
                    st.session_state.bal = float(data["balance"])
                    st.rerun()
                else: st.error("Login fehlgeschlagen.")
    st.stop()

# =================================================================
# 3. SIDEBAR (Stripe & Keys)
# =================================================================
with st.sidebar:
    st.title(f"👋 {st.session_state.user}")
    st.metric("Dein Guthaben", f"{st.session_state.bal:.2f} €")
    
    if st.button("🔄 Guthaben aktualisieren"):
        res = get_user(st.session_state.user)
        if res: 
            st.session_state.bal = float(res["balance"])
            st.rerun()

    st.divider()
    st.subheader("💳 Guthaben aufladen")
    
    # DEIN STRIPE LINK (HIER REINKOPIEREN)
    stripe_link = "https://buy.stripe.com/DEIN_CODE" 
    checkout_url = f"{stripe_link}?prefilled_email={st.session_state.user}"
    
    st.link_button("🚀 10,00 € aufladen", checkout_url, use_container_width=True)

    st.divider()
    gk = st.text_input("Groq API Key", type="password")
    tk = st.text_input("Tavily API Key", type="password")
    if st.button("Abmelden"): 
        st.session_state.logged_in = False
        st.rerun()

# =================================================================
# 4. MAIN ENGINE (Tools & Agent)
# =================================================================
st.title("🤖 Calvin Engine v2.3.1")
prompt = st.text_area("Auftrag:", height=150)

@tool("search_tool")
def search_tool(q: str):
    """Sucht im Web."""
    return TavilySearchResults(api_key=os.environ.get("TAVILY_API_KEY")).run(q)

@tool("pdf_tool")
def pdf_tool(path: str):
    """Liest PDFs."""
    try:
        r = PdfReader(path.strip().replace('"', '').replace('\\', '/'))
        return "".join([p.extract_text() for p in r.pages[:5]])[:3000]
    except Exception as e: return str(e)

if st.button("🚀 Auftrag starten (0,02 €)"):
    if st.session_state.bal < 0.02: st.error("Guthaben leer!")
    elif not gk or not tk: st.warning("Keys fehlen!")
    else:
        with st.status("Verarbeitung..."):
            os.environ["GROQ_API_KEY"], os.environ["TAVILY_API_KEY"] = gk, tk
            try:
                llm = LLM(model="groq/llama-3.3-70b-versatile")
                agent = Agent(role='Analyst', goal=prompt, backstory='AI Executive', tools=[search_tool, pdf_tool], llm=llm)
                res = Crew(agents=[agent], tasks=[Task(description=prompt, expected_output="Bericht", agent=agent)]).kickoff()
                
                st.session_state.bal -= 0.02
                update_bal(st.session_state.user, st.session_state.bal)
                st.info(res.raw)
            except Exception as e: st.error(f"Fehler: {e}")
