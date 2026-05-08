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
# 2. LANDING PAGE & AUTH UI
# =================================================================
st.set_page_config(page_title="Calvin Pro | AI Analyst", layout="wide")

# CSS für den Landingpage-Look
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .hero-text { text-align: center; padding: 50px 0; }
    .hero-title { font-size: 60px; font-weight: 800; color: #deff9a; margin-bottom: 10px; }
    .hero-sub { font-size: 24px; color: #daffde; margin-bottom: 30px; }
    .stButton>button { border-radius: 50px; }
    </style>
    """, unsafe_allow_html=True)

if 'logged_in' not in st.session_state: st.session_state.logged_in = False

if not st.session_state.logged_in:
    # --- LANDING PAGE SECTION ---
    st.markdown('<div class="hero-text">', unsafe_allow_html=True)
    st.markdown('<p class="hero-title">CALVIN <span>PRO</span></p>', unsafe_allow_html=True)
    st.markdown('<p class="hero-sub">Dein persönlicher KI-Business-Analyst. 24/7 einsatzbereit.</p>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
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
                    else: st.error("Login fehlgeschlagen.")
        with tab2:
            st.info("Registrierung ist aktuell über das Admin-Team möglich.")
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

### Was ist neu?
1.  **Landingpage:** Wenn du nicht eingeloggt bist, sieht man jetzt einen großen Hero-Text und eine saubere Login-Maske. Das wirkt direkt professioneller.
2.  **`st.file_uploader`:** Direkt über dem Prompt-Feld gibt es jetzt die Büroklammer zum Hochladen.
3.  **`tempfile` Logik:** Da die KI einen "Pfad" zur Datei braucht, speichern wir die PDF-Daten kurz in einem versteckten Ordner auf dem Streamlit-Server, damit der Agent darauf zugreifen kann. Nach der Analyse wird die Datei automatisch gelöscht.
4.  **Prompt-Injektion:** Wenn du eine Datei hochlädst, sagt die App der KI automatisch: "Hey, da ist ein Dokument, schau da mal rein."


Deine Landingpage-Texte und das PDF-Feature sind bereit. Wie gefällt dir der neue Look?
