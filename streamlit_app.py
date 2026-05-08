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

def update_bal(email, val):
    if supabase:
        supabase.table("profiles").update({"balance": float(val)}).eq("email", email.lower().strip()).execute()


# =================================================================
# 2. SAUBERE LOGIN-MASKE (Für Redirect von Landingpage)
# =================================================================
st.set_page_config(page_title="Calvin Pro Dashboard", layout="centered") # 'centered' sieht beim Login besser aus

if 'logged_in' not in st.session_state: st.session_state.logged_in = False

if not st.session_state.logged_in:
    # Nur ein dezentes Logo oder Titel
    st.title("🔐 Calvin Pro Login")
    
    # Der Stripe-Success-Banner bleibt natürlich
    if st.query_params.get("payment") == "success":
        st.success("🎉 Aufladung erfolgreich! Bitte logge dich ein.")

    tab1, tab2 = st.tabs(["🔑 Einloggen", "📝 Registrieren"])
    with tab1:
        with st.form("login"):
            u = st.text_input("E-Mail").lower().strip()
            p = st.text_input("Passwort", type="password")
            if st.form_submit_button("Anmelden", use_container_width=True):
                data = get_user(u)
                if data and str(data["password"]) == p:
                    st.session_state.logged_in, st.session_state.user = True, u
                    st.session_state.bal = float(data["balance"])
                    st.rerun()
                else: st.error("Daten nicht korrekt.")
    # ... hier den Registrierungs-Tab lassen ...
    st.stop()

# =================================================================
# 3. SIDEBAR & DASHBOARD
# =================================================================
with st.sidebar:
    st.title(f"👋 {st.session_state.user}")
    st.metric("Guthaben", f"{st.session_state.bal:.2f} €")
    
    if st.button("🔄 Aktualisieren"):
        res = get_user(st.session_state.user)
        if res: 
            st.session_state.bal = float(res["balance"])
            st.rerun()

    st.divider()
    st.subheader("💳 Aufladen")
    stripe_link = "https://buy.stripe.com/test_7sYfZg6aF7iX0kkeKN1oI00" 
    st.link_button("🚀 10,00 € aufladen", f"{stripe_link}?prefilled_email={st.session_state.user}", use_container_width=True)
    
    if st.button("Abmelden"): 
        st.session_state.logged_in = False
        st.rerun()

# =================================================================
# 4. TOOLS & ENGINE (Mit PDF-Support)
# =================================================================
st.title("🤖 Calvin Engine v2.4.0")

# --- DATEI UPLOAD ---
uploaded_file = st.file_uploader("Optional: PDF-Dokument zur Analyse hochladen", type="pdf")

prompt = st.text_area("Dein Auftrag an Calvin:", placeholder="Analysiere den Markt für...", height=150)

@tool("search_tool")
def search_tool(q: str):
    """Sucht im Internet nach aktuellen Daten."""
    return TavilySearchResults(api_key=st.secrets["TAVILY_API_KEY"]).run(q)

@tool("pdf_tool")
def pdf_tool(path: str):
    """Liest Text aus einer PDF-Datei."""
    try:
        r = PdfReader(path)
        return "".join([p.extract_text() for p in r.pages[:10]])[:4000]
    except Exception as e: return f"Fehler: {e}"

if st.button("🚀 Auftrag starten (0,02 €)"):
    if st.session_state.bal < 0.02: st.error("Guthaben leer!")
    elif not prompt: st.warning("Auftrag fehlt.")
    else:
        with st.status("Calvin arbeitet...", expanded=True):
            os.environ["GROQ_API_KEY"] = st.secrets["GROQ_API_KEY"]
            os.environ["TAVILY_API_KEY"] = st.secrets["TAVILY_API_KEY"]
            
            # PDF-Handling: Falls eine Datei hochgeladen wurde, speichern wir sie temporär
            temp_pdf_path = None
            if uploaded_file:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(uploaded_file.getvalue())
                    temp_pdf_path = tmp.name
                # Wir ergänzen den Prompt automatisch um den Hinweis auf das PDF
                prompt += f"\n\nNutze zusätzlich die Informationen aus dem hochgeladenen Dokument: {temp_pdf_path}"

            try:
                llm = LLM(model="groq/llama-3.3-70b-versatile")
                calvin = Agent(
                    role='Business Analyst', 
                    goal=prompt, 
                    backstory='KI-Berater für Marktanalysen.', 
                    tools=[search_tool, pdf_tool], 
                    llm=llm
                )
                res = Crew(agents=[calvin], tasks=[Task(description=prompt, expected_output="Bericht", agent=calvin)]).kickoff()
                
                # Abrechnung
                st.session_state.bal -= 0.02
                update_bal(st.session_state.user, st.session_state.bal)
                
                st.subheader("Analyse-Ergebnis:")
                st.info(res.raw)
                
                # Temp Datei löschen
                if temp_pdf_path: os.unlink(temp_pdf_path)
                
            except Exception as e: st.error(f"Fehler: {e}")



