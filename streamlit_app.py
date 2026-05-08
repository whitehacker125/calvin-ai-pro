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

def register_user(email, password):
    if not supabase: return False, "DB-Verbindung fehlt."
    if get_user(email): return False, "E-Mail existiert bereits."
    try:
        # Erstellt den Nutzer mit 10.00 € Startguthaben
        supabase.table("profiles").insert({
            "email": email.lower().strip(), 
            "password": password, 
            "balance": 10.00
        }).execute()
        return True, "Konto erfolgreich erstellt! Bitte jetzt einloggen."
    except Exception as e:
        return False, str(e)

def update_bal(email, val):
    if supabase:
        supabase.table("profiles").update({"balance": float(val)}).eq("email", email).execute()

# =================================================================
# 2. AUTHENTICATION UI (Login & Registrierung)
# =================================================================
st.set_page_config(page_title="Calvin Pro Business", layout="wide")

# Prüfe, ob wir gerade von Stripe kommen
query_params = st.query_params
if query_params.get("payment") == "success":
    st.success("🎉 Zahlung erfolgreich! Bitte logge dich ein, um dein neues Guthaben zu sehen.")

if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user' not in st.session_state: st.session_state.user = ""
if 'bal' not in st.session_state: st.session_state.bal = 0.0

if not st.session_state.logged_in:
    st.title("🔐 Calvin Pro - Business Engine")
    tab1, tab2 = st.tabs(["🔑 Login", "📝 Registrierung"])
    
    with tab1:
        with st.form("login_form"):
            u = st.text_input("E-Mail").lower().strip()
            p = st.text_input("Passwort", type="password")
            if st.form_submit_button("Anmelden", use_container_width=True):
                data = get_user(u)
                if data and str(data["password"]) == p:
                    st.session_state.logged_in = True
                    st.session_state.user = u
                    st.session_state.bal = float(data["balance"])
                    st.rerun()
                else:
                    st.error("Login fehlgeschlagen. Bitte Daten prüfen.")
    
    with tab2:
        with st.form("register_form"):
            new_u = st.text_input("Neue E-Mail").lower().strip()
            new_p = st.text_input("Neues Passwort", type="password")
            confirm_p = st.text_input("Passwort bestätigen", type="password")
            if st.form_submit_button("Konto erstellen", use_container_width=True):
                if new_p != confirm_p:
                    st.error("Passwörter stimmen nicht überein.")
                elif len(new_p) < 6:
                    st.error("Passwort muss mindestens 6 Zeichen haben.")
                elif "@" not in new_u:
                    st.error("Bitte eine gültige E-Mail angeben.")
                else:
                    success, msg = register_user(new_u, new_p)
                    if success:
                        st.success(msg)
                    else:
                        st.error(msg)
    
    st.stop() # Beendet das Skript hier, solange man nicht eingeloggt ist

# =================================================================
# 3. SIDEBAR (Dashboard & Stripe)
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
    
    # --- DEIN STRIPE LINK ---
    stripe_link = "https://buy.stripe.com/test_7sYfZg6aF7iX0kkeKN1oI00" 
    checkout_url = f"{stripe_link}?prefilled_email={st.session_state.user}"
    
    st.link_button("🚀 10,00 € aufladen", checkout_url, use_container_width=True)

    st.divider()
    gk = st.text_input("Groq API Key", type="password")
    tk = st.text_input("Tavily API Key", type="password")
    if st.button("Abmelden"): 
        st.session_state.logged_in = False
        st.rerun()

# =================================================================
# 4. MAIN ENGINE
# =================================================================
st.title("🤖 Calvin Engine v2.3.2")
prompt = st.text_area("Auftrag an Calvin:", placeholder="Was soll analysiert werden?", height=150)

@tool("search_tool")
def search_tool(q: str):
    """Sucht im Internet nach aktuellen Daten."""
    return TavilySearchResults(api_key=os.environ.get("TAVILY_API_KEY")).run(q)

@tool("pdf_tool")
def pdf_tool(path: str):
    """Liest Text aus einer PDF-Datei."""
    try:
        r = PdfReader(path.strip().replace('"', '').replace('\\', '/'))
        text = "".join([p.extract_text() for p in r.pages[:5]])
        return text[:3000]
    except Exception as e:
        return f"Fehler beim PDF-Lesen: {str(e)}"

if st.button("🚀 Auftrag starten (0,02 €)"):
    if st.session_state.bal < 0.02:
        st.error("Guthaben leer! Bitte aufladen.")
    elif not gk or not tk:
        st.warning("Bitte Groq- und Tavily-Keys in der Sidebar eingeben.")
    elif not prompt:
        st.warning("Bitte gib einen Auftrag ein.")
    else:
        with st.status("Calvin arbeitet..."):
            os.environ["GROQ_API_KEY"] = gk
            os.environ["TAVILY_API_KEY"] = tk
            try:
                llm = LLM(model="groq/llama-3.3-70b-versatile")
                agent = Agent(
                    role='Business Analyst', 
                    goal=prompt, 
                    backstory='KI-Berater für Marktanalysen und Dokumente.', 
                    tools=[search_tool, pdf_tool], 
                    llm=llm
                )
                res = Crew(agents=[agent], tasks=[Task(description=prompt, expected_output="Bericht", agent=agent)]).kickoff()
                
                # Abrechnung
                st.session_state.bal -= 0.02
                update_bal(st.session_state.user, st.session_state.bal)
                
                st.subheader("Ergebnis:")
                st.info(res.raw)
                st.toast("0,02 € abgebucht.")
            except Exception as e:
                st.error(f"Fehler: {e}")
