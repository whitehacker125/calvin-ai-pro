import streamlit as st
import os
import shutil
from supabase import create_client, Client
from crewai import Agent, Task, Crew, Process, LLM
from crewai.tools import tool
from langchain_community.tools.tavily_search import TavilySearchResults
from pypdf import PdfReader

# =================================================================
# 1. CLOUD-VERBINDUNG (Secrets Management)
# =================================================================
def connect_supabase():
    try:
        # Diese Werte müssen in den Advanced Settings -> Secrets der App stehen
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception:
        return None

supabase = connect_supabase()

# --- DATENBANK LOGIK ---
def get_user(email):
    if not supabase: return None
    try:
        res = supabase.table("profiles").select("*").eq("email", email).execute()
        return res.data[0] if res.data else None
    except: return None

def signup(email, pwd):
    if get_user(email): return False, "Konto existiert bereits."
    try:
        # Startguthaben 10.00 Euro für neue Cloud-Nutzer
        supabase.table("profiles").insert({"email": email, "password": pwd, "balance": 10.00}).execute()
        return True, "Registrierung erfolgreich! Bitte logge dich ein."
    except Exception as e: return False, str(e)

def update_bal(email, bal):
    if supabase:
        try:
            supabase.table("profiles").update({"balance": float(bal)}).eq("email", email).execute()
        except: pass

# =================================================================
# 2. UI & LOGIN BEREICH
# =================================================================
st.set_page_config(page_title="Calvin Pro Business", layout="wide")

if not supabase:
    st.title("🤖 Calvin Cloud Setup")
    st.error("⚠️ Datenbank nicht verbunden. Bitte prüfe die 'Secrets' in den Streamlit Advanced Settings!")
    st.info("Format: SUPABASE_URL = '...' und SUPABASE_KEY = '...'")
    st.stop()

if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user' not in st.session_state: st.session_state.user = ""
if 'bal' not in st.session_state: st.session_state.bal = 0.0

if not st.session_state.logged_in:
    st.title("🔐 Calvin Pro - Enterprise Cloud")
    t1, t2 = st.tabs(["🔑 Login", "📝 Registrieren"])
    with t1:
        with st.form("login_form"):
            u_in = st.text_input("E-Mail").lower().strip()
            p_in = st.text_input("Passwort", type="password")
            if st.form_submit_button("Anmelden", use_container_width=True):
                data = get_user(u_in)
                if data and str(data["password"]) == p_in:
                    st.session_state.logged_in, st.session_state.user = True, u_in
                    st.session_state.bal = float(data["balance"])
                    st.rerun()
                else: st.error("Login-Daten inkorrekt.")
    with t2:
        with st.form("reg_form"):
            nu, np = st.text_input("E-Mail").lower().strip(), st.text_input("Passwort", type="password")
            if st.form_submit_button("Konto erstellen"):
                if "@" in nu and len(np) >= 6:
                    s, m = signup(nu, np)
                    if s: st.success(m)
                    else: st.error(m)
                else: st.error("E-Mail ungültig oder Passwort zu kurz (min. 6 Zeichen).")
    st.stop()

# =================================================================
# 3. SIDEBAR & BENUTZER-DASHBOARD
# =================================================================
with st.sidebar:
    st.title(f"👋 {st.session_state.user}")
    st.metric("Dein Guthaben", f"{st.session_state.bal:.2f} €")
    if st.button("🔄 Guthaben aktualisieren"):
        res = get_user(st.session_state.user)
        if res: st.session_state.bal = float(res["balance"]); st.rerun()
    st.divider()
    gk = st.text_input("Groq API Key", type="password", help="Dein Key von console.groq.com")
    tk = st.text_input("Tavily API Key", type="password", help="Dein Key von tavily.com")
    if st.button("Abmelden"): 
        st.session_state.logged_in = False
        st.rerun()

st.title("🤖 Calvin Engine v2.2 (Cloud Live)")
prompt = st.text_area("Was soll Calvin analysieren?", placeholder="Geben Sie hier Ihren Auftrag ein...", height=150)

# =================================================================
# 4. KI-TOOLS (Agenten-Fähigkeiten)
# =================================================================

@tool("search_tool")
def search_tool(q: str):
    """Sucht im Internet nach aktuellen Daten und Informationen."""
    # Tavily nutzt den Key aus der Umgebungsvariable (wird beim Start gesetzt)
    return TavilySearchResults(api_key=os.environ.get("TAVILY_API_KEY")).run(q)

@tool("pdf_reader_tool")
def pdf_reader_tool(pdf_path: str):
    """Extrahiert Text aus PDF-Dateien für die Analyse (Cloud-kompatibel)."""
    try:
        # Bereinigung des Pfades
        clean_path = pdf_path.strip().replace('"', '').replace("'", "").replace('\\', '/')
        if not os.path.exists(clean_path):
            return f"Fehler: Datei unter {clean_path} nicht gefunden."
            
        reader = PdfReader(clean_path)
        content = ""
        for i, page in enumerate(reader.pages):
            if i > 5: break # Token-Limit Schutz
            content += page.extract_text()
            
        return f"PDF-Inhalt (Auszug):\n\n{content[:4000]}"
    except Exception as e:
        return f"Fehler beim PDF-Lesen: {str(e)}"

# =================================================================
# 5. AGENTEN-LOGIK & ABRECHNUNG
# =================================================================
if st.button("🚀 Auftrag zahlungspflichtig starten (0,02 €)"):
    if st.session_state.bal < 0.02: 
        st.error("Guthaben leer! Bitte lade dein Konto auf.")
    elif not gk or not tk: 
        st.warning("Bitte gib beide API-Keys in der Sidebar ein.")
    elif not prompt: 
        st.warning("Bitte gib einen Auftrag für Calvin ein.")
    else:
        with st.status("Calvin kontaktiert die Cloud-Engine...", expanded=True):
            # API Keys in die Umgebung laden
            os.environ["GROQ_API_KEY"] = gk
            os.environ["TAVILY_API_KEY"] = tk
            
            try:
                # Das modernste Groq-Modell
                llm = LLM(model="groq/llama-3.3-70b-versatile")
                
                # Agenten-Setup
                calvin_analyst = Agent(
                    role='Senior Executive Consultant', 
                    goal=f'Löse die Aufgabe präzise: {prompt}', 
                    backstory='Du bist ein hochbezahlter Analyst. Du nutzt Internet-Suche und PDF-Daten für perfekte Ergebnisse.',
                    tools=[search_tool, pdf_reader_tool], 
                    llm=llm,
                    allow_delegation=False
                )
                
                # Auftrag definieren
                analysis_task = Task(
                    description=f"Kundenauftrag: {prompt}", 
                    expected_output="Ein professioneller, gut strukturierter Ergebnisbericht.", 
                    agent=calvin_analyst
                )
                
                # Crew starten
                calvin_crew = Crew(agents=[calvin_analyst], tasks=[analysis_task])
                final_result = calvin_crew.kickoff()
                
                # --- ABRECHNUNG ÜBER SUPABASE ---
                st.session_state.bal -= 0.02
                update_bal(st.session_state.user, st.session_state.bal)
                
                st.subheader("Ergebnis von Calvin:")
                st.info(final_result.raw)
                st.toast("Auftrag abgeschlossen: 0,02 € wurden abgerechnet.", icon="💸")
                
            except Exception as e:
                st.error(f"Ein technischer Fehler ist aufgetreten: {e}")

st.divider()
st.caption("Calvin Enterprise v2.2 | Powered by Groq & Supabase | 24/7 Cloud Access")
