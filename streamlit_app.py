import streamlit as st
import os
import tempfile
from supabase import create_client, Client
from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import tool
from langchain_community.tools.tavily_search import TavilySearchResults
from pypdf import PdfReader

# =================================================================
# 1. DATABASE & INITIALIZATION
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
        r = supabase.table("profiles").select("*").eq("email", email.lower().strip()).execute()
        return r.data[0] if r.data else None
    except: return None

def register_user(email, password):
    if not supabase: return False, "Datenbankverbindung fehlt."
    if get_user(email): return False, "Diese E-Mail ist bereits registriert."
    try:
        supabase.table("profiles").insert({
            "email": email.lower().strip(), 
            "password": password, 
            "balance": 10.00
        }).execute()
        return True, "Konto erstellt! Bitte logge dich jetzt ein."
    except Exception as e:
        return False, str(e)

def update_bal(email, val):
    if supabase:
        supabase.table("profiles").update({"balance": float(val)}).eq("email", email.lower().strip()).execute()

# =================================================================
# 2. LOGIN-SYSTEM (VERKNÜPFT MIT CARRD)
# =================================================================
st.set_page_config(page_title="Calvin Pro Dashboard", layout="centered")

# CSS für professionellen Login-Look
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; }
    h1 { color: #deff9a; text-align: center; font-family: 'Helvetica', sans-serif; }
    .stButton>button { width: 100%; border-radius: 20px; }
    </style>
    """, unsafe_allow_html=True)

if 'logged_in' not in st.session_state: st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🤖 Calvin Pro Login")
    
    # Stripe Check
    if st.query_params.get("payment") == "success":
        st.success("🎉 Aufladung erfolgreich! Bitte logge dich ein, um dein Guthaben zu sehen.")

    tab1, tab2 = st.tabs(["🔑 Login", "📝 Registrierung"])
    
    with tab1:
        with st.form("login_form"):
            u = st.text_input("E-Mail").lower().strip()
            p = st.text_input("Passwort", type="password")
            if st.form_submit_button("Anmelden"):
                data = get_user(u)
                if data and str(data["password"]) == p:
                    st.session_state.logged_in, st.session_state.user = True, u
                    st.session_state.bal = float(data["balance"])
                    st.rerun()
                else: st.error("E-Mail oder Passwort falsch.")
    
    with tab2:
        with st.form("reg_form"):
            new_u = st.text_input("E-Mail Adresse").lower().strip()
            new_p = st.text_input("Passwort wählen", type="password")
            confirm_p = st.text_input("Passwort bestätigen", type="password")
            if st.form_submit_button("Konto erstellen"):
                if new_p != confirm_p: st.error("Passwörter ungleich.")
                elif len(new_p) < 6: st.error("Passwort zu kurz (min. 6 Zeichen).")
                else:
                    ok, msg = register_user(new_u, new_p)
                    if ok: st.success(msg)
                    else: st.error(msg)
    
    st.markdown("---")
    st.link_button("🏠 Zurück zur Website", "https://calvinpro.carrd.co/", use_container_width=True)
    st.stop()

# =================================================================
# 3. DAS DASHBOARD (Nach erfolgreichem Login)
# =================================================================
# Zurück auf 'wide' schalten für die Analyse-Ansicht
# Hinweis: st.set_page_config kann nur einmal aufgerufen werden, 
# daher simulieren wir die Breite hier über das Dashboard-Design.

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
    stripe_link = "https://buy.stripe.com/test_7sYfZg6aF7iX0kkeKN1oI00" 
    st.link_button("🚀 10,00 € aufladen", f"{stripe_link}?prefilled_email={st.session_state.user}", use_container_width=True)

    if st.button("Abmelden"): 
        st.session_state.logged_in = False
        st.rerun()

# =================================================================
# 4. ENGINE & TOOLS (PDF-Support inklusive)
# =================================================================
st.header("🤖 Calvin Engine v2.4.5")

uploaded_file = st.file_uploader("PDF-Dokument hochladen (Optional)", type="pdf")
prompt = st.text_area("Analyse-Auftrag:", placeholder="Worüber soll Calvin recherchieren?", height=150)

@tool("search_tool")
def search_tool(q: str):
    """Sucht im Internet."""
    return TavilySearchResults(api_key=st.secrets["TAVILY_API_KEY"]).run(q)

@tool("pdf_tool")
def pdf_tool(path: str):
    """Liest PDFs aus."""
    try:
        r = PdfReader(path)
        return "".join([p.extract_text() for p in r.pages[:10]])[:4000]
    except Exception as e: return f"PDF-Fehler: {e}"

if st.button("🚀 Analyse starten (0,02 €)"):
    if st.session_state.bal < 0.02: st.error("Guthaben leer!")
    elif not prompt: st.warning("Bitte gib einen Auftrag ein.")
    else:
        with st.status("Calvin arbeitet...", expanded=True):
            os.environ["GROQ_API_KEY"] = st.secrets["GROQ_API_KEY"]
            os.environ["TAVILY_API_KEY"] = st.secrets["TAVILY_API_KEY"]
            
            temp_pdf_path = None
            if uploaded_file:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(uploaded_file.getvalue())
                    temp_pdf_path = tmp.name
                prompt += f"\n\nAnalysiere zusätzlich dieses Dokument: {temp_pdf_path}"

            try:
                llm = LLM(model="groq/llama-3.3-70b-versatile")
                calvin = Agent(
                    role='Business Analyst', 
                    goal=prompt, 
                    backstory='KI-Berater für Business-Insights.', 
                    tools=[search_tool, pdf_tool], 
                    llm=llm
                )
                res = Crew(agents=[calvin], tasks=[Task(description=prompt, expected_output="Bericht", agent=calvin)]).kickoff()
                
                st.session_state.bal -= 0.02
                update_bal(st.session_state.user, st.session_state.bal)
                
                st.subheader("Calvins Bericht:")
                st.info(res.raw)
                if temp_pdf_path: os.unlink(temp_pdf_path)
            except Exception as e: st.error(f"Fehler: {e}")
