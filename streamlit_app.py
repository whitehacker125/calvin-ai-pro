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
        # Greift auf die Secrets in Streamlit Cloud zu
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
    if not supabase: return False, "Datenbankverbindung fehlgeschlagen."
    if get_user(email): return False, "Ein Konto mit dieser E-Mail existiert bereits."
    try:
        # Erstellt den Nutzer mit 10.00 € Startguthaben
        supabase.table("profiles").insert({
            "email": email.lower().strip(), 
            "password": password, 
            "balance": 10.00
        }).execute()
        return True, "Konto erfolgreich erstellt! Du kannst dich jetzt einloggen."
    except Exception as e:
        return False, str(e)

def update_bal(email, val):
    if supabase:
        supabase.table("profiles").update({"balance": float(val)}).eq("email", email.lower().strip()).execute()

# =================================================================
# 2. AUTHENTICATION & REDIRECT LOGIC
# =================================================================
st.set_page_config(page_title="Calvin Pro Business", layout="wide")

# Parameter aus der URL abfangen (für Rückkehrer von Stripe)
query_params = st.query_params
url_email = query_params.get("user_email", "")
payment_status = query_params.get("payment", "")

if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'user' not in st.session_state: st.session_state.user = ""
if 'bal' not in st.session_state: st.session_state.bal = 0.0

# Wenn nicht eingeloggt, zeige die Auth-Maske
if not st.session_state.logged_in:
    st.title("🔐 Calvin Pro - Business Engine")
    
    # Erfolgsmeldung nach Stripe-Rückkehr
    if payment_status == "success":
        st.success("🎉 Zahlung erfolgreich! Dein Guthaben wurde aufgeladen. Bitte logge dich ein, um fortzufahren.")
    
    tab1, tab2 = st.tabs(["🔑 Login", "📝 Registrierung"])
    
    with tab1:
        with st.form("login_form"):
            # Falls wir von Stripe kommen, steht die E-Mail schon drin
            default_email = url_email if url_email else ""
            u = st.text_input("E-Mail", value=default_email).lower().strip()
            p = st.text_input("Passwort", type="password")
            if st.form_submit_button("Anmelden", use_container_width=True):
                data = get_user(u)
                if data and str(data["password"]) == p:
                    st.session_state.logged_in = True
                    st.session_state.user = u
                    st.session_state.bal = float(data["balance"])
                    st.rerun()
                else:
                    st.error("E-Mail oder Passwort falsch.")
    
    with tab2:
        with st.form("register_form"):
            new_u = st.text_input("E-Mail Adresse").lower().strip()
            new_p = st.text_input("Passwort wählen", type="password")
            confirm_p = st.text_input("Passwort bestätigen", type="password")
            if st.form_submit_button("Konto erstellen", use_container_width=True):
                if new_p != confirm_p:
                    st.error("Die Passwörter stimmen nicht überein.")
                elif len(new_p) < 6:
                    st.error("Das Passwort muss mindestens 6 Zeichen lang sein.")
                elif "@" not in new_u:
                    st.error("Bitte gib eine gültige E-Mail Adresse ein.")
                else:
                    success, msg = register_user(new_u, new_p)
                    if success:
                        st.success(msg)
                    else:
                        st.error(msg)
    
    st.stop() # App hier anhalten, bis Login erfolgt ist

# =================================================================
# 3. SIDEBAR (Benutzer-Dashboard & Stripe)
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
    
    # Stripe Link mit Prefill der E-Mail
    # Ersetze 'DEIN_STRIPE_LINK' durch deinen echten Payment-Link
    stripe_base_url = "https://buy.stripe.com/test_7sYfZg6aF7iX0kkeKN1oI00" 
    checkout_url = f"{stripe_base_url}?prefilled_email={st.session_state.user}"
    
    st.link_button("🚀 10,00 € aufladen", checkout_url, use_container_width=True)
    st.caption("Abwicklung sicher über Stripe")

    st.divider()
    gk = st.text_input("Groq API Key", type="password", help="Dein Key von console.groq.com")
    tk = st.text_input("Tavily API Key", type="password", help="Dein Key von tavily.com")
    
    if st.button("Abmelden"): 
        st.session_state.logged_in = False
        st.rerun()

# =================================================================
# 4. MAIN ENGINE (KI-Agenten)
# =================================================================
st.title("🤖 Calvin Engine v2.3.5")
prompt = st.text_area("Was soll Calvin heute für dich tun?", placeholder="Analysiere den Markt für...", height=150)

@tool("search_tool")
def search_tool(q: str):
    """Sucht im Internet nach aktuellen Informationen."""
    return TavilySearchResults(api_key=os.environ.get("TAVILY_API_KEY")).run(q)

@tool("pdf_tool")
def pdf_tool(path: str):
    """Extrahiert Text aus PDF-Dokumenten."""
    try:
        r = PdfReader(path.strip().replace('"', '').replace('\\', '/'))
        text = "".join([p.extract_text() for p in r.pages[:5]])
        return text[:3000]
    except Exception as e:
        return f"Fehler beim Lesen des PDFs: {e}"

if st.button("🚀 Auftrag starten (0,02 €)"):
    if st.session_state.bal < 0.02:
        st.error("Guthaben nicht ausreichend! Bitte lade dein Konto auf.")
    elif not gk or not tk:
        st.warning("Bitte gib deine API-Keys in der Sidebar ein.")
    elif not prompt:
        st.warning("Kein Auftrag eingegeben.")
    else:
        with st.status("Calvin analysiert...", expanded=True):
            os.environ["GROQ_API_KEY"] = gk
            os.environ["TAVILY_API_KEY"] = tk
            try:
                llm = LLM(model="groq/llama-3.3-70b-versatile")
                
                calvin = Agent(
                    role='Business Analyst', 
                    goal=prompt, 
                    backstory='Du bist Calvin, ein KI-Experte für Business-Analysen.', 
                    tools=[search_tool, pdf_tool], 
                    llm=llm
                )
                
                task = Task(description=prompt, expected_output="Ein detaillierter Bericht.", agent=calvin)
                crew = Crew(agents=[calvin], tasks=[task])
                result = crew.kickoff()
                
                # Guthaben abziehen
                st.session_state.bal -= 0.02
                update_bal(st.session_state.user, st.session_state.bal)
                
                st.subheader("Calvins Analyse-Ergebnis:")
                st.info(result.raw)
                st.toast("0,02 € erfolgreich abgerechnet.")
                
            except Exception as e:
                st.error(f"Ein Fehler ist aufgetreten: {e}")

st.divider()
st.caption("Calvin Enterprise SaaS | v2.3.5")
