import streamlit as st
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor

# Seiteneinstellungen
st.set_page_config(page_title="Unser Urlaubsplaner 🌍", layout="wide")

# 1. Datenbank-Verbindung (Sicher über Streamlit Secrets)
def get_db():
    return psycopg2.connect(st.secrets["DATABASE_URL"], cursor_factory=RealDictCursor)

# 2. Initialisierung der Tabellen
def init_db():
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('''CREATE TABLE IF NOT EXISTS users 
                       (id SERIAL PRIMARY KEY, username TEXT UNIQUE, password TEXT)''')
        cur.execute('''CREATE TABLE IF NOT EXISTS trips 
                       (id SERIAL PRIMARY KEY, title TEXT, destination TEXT, 
                        start_date TEXT, end_date TEXT, status TEXT, notes TEXT DEFAULT '', owner_id INTEGER)''')
        cur.execute('''CREATE TABLE IF NOT EXISTS trip_collaborators 
                       (trip_id INTEGER, user_id INTEGER, PRIMARY KEY (trip_id, user_id))''')
        cur.execute('''CREATE TABLE IF NOT EXISTS todos 
                       (id SERIAL PRIMARY KEY, trip_id INTEGER, task TEXT, done INTEGER DEFAULT 0, type TEXT DEFAULT 'task')''')
        cur.execute('''CREATE TABLE IF NOT EXISTS expenses 
                       (id SERIAL PRIMARY KEY, trip_id INTEGER, amount REAL, category TEXT, description TEXT)''')
        cur.execute('''CREATE TABLE IF NOT EXISTS itinerary 
                       (id SERIAL PRIMARY KEY, trip_id INTEGER, activity_date TEXT, activity_time TEXT, activity TEXT)''')
        conn.commit()
    conn.close()

init_db()

# Session States initialisieren
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
    st.session_state["user_id"] = None
    st.session_state["username"] = ""
if "current_trip_id" not in st.session_state:
    st.session_state["current_trip_id"] = None

# --- DYNAMISCHES LOGIN & REGISTRIERUNGS-FENSTER ---
def show_login():
    st.title("🔒 Unser Urlaubsplaner")
    
    tab1, tab2 = st.tabs(["🔑 Einloggen", "📝 Registrieren"])
    
    with tab1:
        with st.form("login_form"):
            username = st.text_input("Benutzername")
            password = st.text_input("Passwort", type="password")
            submit = st.form_submit_button("Einloggen")
            
            if submit:
                conn = get_db()
                with conn.cursor() as cur:
                    cur.execute("SELECT id, password FROM users WHERE username = %s", (username,))
                    user = cur.fetchone()
                    if user and user['password'] == password:
                        st.session_state["logged_in"] = True
                        st.session_state["user_id"] = user['id']
                        st.session_state["username"] = username
                        st.success("Erfolgreich eingeloggt!")
                        st.rerun()
                    else:
                        st.error("Falscher Benutzername oder Passwort!")
                conn.close()
                
    with tab2:
        with st.form("register_form"):
            new_username = st.text_input("Wunsch-Benutzername")
            new_password = st.text_input("Passwort wählen", type="password")
            submit_reg = st.form_submit_button("Konto erstellen")
            
            if submit_reg and new_username and new_password:
                conn = get_db()
                with conn.cursor() as cur:
                    try:
                        cur.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (new_username, new_password))
                        conn.commit()
                        st.success("Konto erfolgreich erstellt! Du kannst dich jetzt einloggen.")
                    except:
                        st.error("Dieser Benutzername ist leider schon vergeben.")
                conn.close()

# --- SEITE 1: ÜBERSICHT (GEFILTERT NACH USER) ---
def show_overview():
    st.title(f"🌍 Urlaubsplaner von {st.session_state['username']}")
    user_id = st.session_state["user_id"]
    
    # Daten abrufen (Nur eigene Trips ODER Trips wo man Collaborator ist)
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('''
            SELECT t.* FROM trips t
            LEFT JOIN trip_collaborators c ON t.id = c.trip_id
            WHERE t.owner_id = %s OR c.user_id = %s
            GROUP BY t.id
        ''', (user_id, user_id))
        trips_raw = cur.fetchall()
        
        # Finanzen nur für die sichtbaren Trips berechnen
        visible_trip_ids = [t['id'] for t in trips_raw]
        if visible_trip_ids:
            cur.execute('SELECT amount, category FROM expenses WHERE trip_id = ANY(%s)', (visible_trip_ids,))
            all_expenses = cur.fetchall()
        else:
            all_expenses = []
    conn.close()
    
    # Berechnungen für das Finanz-Dashboard
    total_all_trips = sum(exp['amount'] for exp in all_expenses)
    category_totals = {'Transport': 0.0, 'Unterkunft': 0.0, 'Verpflegung': 0.0, 'Aktivitäten': 0.0}
    for exp in all_expenses:
        cat = exp['category']
        if cat in category_totals:
            category_totals[cat] += exp['amount']

    # 💰 FINANZ-DASHBOARD
    st.header("💰 Mein Finanz-Dashboard")
    col_total, col_cats = st.columns([1, 2])
    with col_total:
        st.metric(label="Gesamtausgaben deiner Trips", value=f"{total_all_trips:.2f} €")
    with col_cats:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("✈️ Transport", f"{category_totals['Transport']:.2f} €")
        c2.metric("🏨 Unterkunft", f"{category_totals['Unterkunft']:.2f} €")
        c3.metric("🍕 Essen", f"{category_totals['Verpflegung']:.2f} €")
        c4.metric("🎟️ Freizeit", f"{category_totals['Aktivitäten']:.2f} €")
        
    st.markdown("---")
    
    # ➕ NEUEN TRIP PLANEN (Man wird automatisch Owner)
    with st.expander("➕ Neuen Trip planen"):
        with st.form("add_trip_form"):
            title = st.text_input("Titel (z.B. Roadtrip durch Italien)")
            destination = st.text_input("Zielort")
            start_date = st.date_input("Startdatum")
            end_date = st.date_input("Enddatum")
            status = st.selectbox("Status", ["💡 Idee", "📅 Gebucht", "✅ Abgeschlossen"])
            submit = st.form_submit_button("Trip speichern")
            
            if submit and title and destination:
                conn = get_db()
                with conn.cursor() as cur:
                    cur.execute('INSERT INTO trips (title, destination, start_date, end_date, status, owner_id) VALUES (%s, %s, %s, %s, %s, %s)', 
                                (title, destination, str(start_date), str(end_date), status, user_id))
                    conn.commit()
                conn.close()
                st.success("Trip gespeichert!")
                st.rerun()

    # 🗺️ GEPLANTE TRIPS ANZEIGEN
    st.header("Meine Urlaube")
    today = datetime.now().date()
    
    for trip in trips_raw:
        try:
            s_date = datetime.strptime(trip['start_date'], '%Y-%m-%d').date()
            e_date = datetime.strptime(trip['end_date'], '%Y-%m-%d').date()
            if today < s_date:
                countdown = f"⏳ Noch {(s_date - today).days} Tage"
            elif s_date <= today <= e_date:
                countdown = "✈️ Aktuell im Urlaub!"
            else:
                countdown = "✅ Vorbeigezogen"
        except:
            countdown = "Kein Datum"
            
        with st.container(border=True):
            c_left, c_right = st.columns([4, 1])
            with c_left:
                role = "👑 Ersteller" if trip['owner_id'] == user_id else "👥 Eingeladen"
                st.subheader(f"{trip['title']} ({trip['status']}) - *{role}*")
                st.write(f"📍 {trip['destination']} | 📅 {trip['start_date']} bis {trip['end_date']} | **{countdown}**")
            with c_right:
                if st.button("Details öffnen 📂", key=f"open_{trip['id']}"):
                    st.session_state["current_trip_id"] = trip['id']
                    st.rerun()
                # Nur der Owner darf den kompletten Trip löschen
                if trip['owner_id'] == user_id:
                    if st.button("Löschen ❌", key=f"del_{trip['id']}"):
                        conn = get_db()
                        with conn.cursor() as cur:
                            cur.execute('DELETE FROM trips WHERE id = %s', (trip['id'],))
                            cur.execute('DELETE FROM todos WHERE trip_id = %s', (trip['id'],))
                            cur.execute('DELETE FROM expenses WHERE trip_id = %s', (trip['id'],))
                            cur.execute('DELETE FROM itinerary WHERE trip_id = %s', (trip['id'],))
                            cur.execute('DELETE FROM trip_collaborators WHERE trip_id = %s', (trip['id'],))
                            conn.commit()
                        conn.close()
                        st.rerun()

# --- SEITE 2: DETAILANSICHT WITH COLLABORATORS ---
def show_detail(trip_id):
    user_id = st.session_state["user_id"]
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('SELECT * FROM trips WHERE id = %s', (trip_id,))
        trip = cur.fetchone()
        cur.execute('SELECT * FROM todos WHERE trip_id = %s AND type = \'task\'', (trip_id,))
        todos = cur.fetchall()
        cur.execute('SELECT * FROM todos WHERE trip_id = %s AND type = \'pack\'', (trip_id,))
        packing_list = cur.fetchall()
        cur.execute('SELECT * FROM expenses WHERE trip_id = %s', (trip_id,))
        expenses = cur.fetchall()
        cur.execute('SELECT * FROM itinerary WHERE trip_id = %s ORDER BY activity_date ASC, activity_time ASC', (trip_id,))
        itinerary_raw = cur.fetchall()
        # Aktuelle Collaborators holen
        cur.execute('SELECT u.username FROM trip_collaborators c JOIN users u ON c.user_id = u.id WHERE c.trip_id = %s', (trip_id,))
        collaborators = cur.fetchall()
    conn.close()
    
    if st.button("← Zurück zur Übersicht"):
        st.session_state["current_trip_id"] = None
        st.rerun()
        
    st.title(trip['title'])
    st.write(f"📍 **Ziel:** {trip['destination']} | 📅 {trip['start_date']} bis {trip['end_date']}")
    
    # 👥 COLLABORATOR MANAGEMENT
    st.markdown("---")
    st.header("👥 Mitreisende & Freunde einladen")
    
    c_list, c_invite = st.columns([1, 1])
    with c_list:
        st.write("**Mitglieder in diesem Projekt:**")
        st.write(f"- 👑 (Ersteller)")
        for colab in collaborators:
            st.write(f"- 👥 {colab['username']}")
            
    with c_invite:
        # Nur der Owner kann Leute einladen
        if trip['owner_id'] == user_id:
            with st.form("invite_form"):
                friend_name = st.text_input("Benutzername des Freundes")
                submit_invite = st.form_submit_button("Zum Trip hinzufügen")
                
                if submit_invite and friend_name:
                    conn = get_db()
                    with conn.cursor() as cur:
                        cur.execute("SELECT id FROM users WHERE username = %s", (friend_name,))
                        friend = cur.fetchone()
                        if friend:
                            if friend['id'] == user_id:
                                st.warning("Du bist bereits der Ersteller dieses Trips.")
                            else:
                                try:
                                    cur.execute("INSERT INTO trip_collaborators (trip_id, user_id) VALUES (%s, %s)", (trip_id, friend['id']))
                                    conn.commit()
                                    st.success(f"{friend_name} wurde hinzugefügt!")
                                    st.rerun()
                                except:
                                    st.info("Dieser Nutzer ist bereits im Projekt.")
                        else:
                            st.error("Benutzername nicht gefunden. Dein Freund muss sich zuerst registrieren!")
                    conn.close()
        else:
            st.info("Nur der Ersteller des Trips kann weitere Freunde einladen.")

    st.markdown("---")
    
    # 📅 REISE-KALENDER
    st.header("📅 Reise-Kalender")
    with st.form("add_activity_form"):
        c1, c2, c3 = st.columns([1, 1, 2])
        a_date = c1.date_input("Datum", value=datetime.strptime(trip['start_date'], '%Y-%m-%d').date())
        a_time = c2.time_input("Uhrzeit")
        a_text = c3.text_input("Neue Aktivität (z.B. Strand-Tag)")
        submit_act = st.form_submit_button("+ Event hinzufügen")
        
        if submit_act and a_text:
            conn = get_db()
            with conn.cursor() as cur:
                cur.execute('INSERT INTO itinerary (trip_id, activity_date, activity_time, activity) VALUES (%s, %s, %s, %s)', 
                            (trip_id, str(a_date), str(a_time)[:5], a_text))
                conn.commit()
            conn.close()
            st.rerun()
            
    calendar_data = {}
    for item in itinerary_raw:
        date_str = item['activity_date']
        if date_str not in calendar_data:
            calendar_data[date_str] = []
        calendar_data[date_str].append(item)
        
    if calendar_data:
        cols = st.columns(len(calendar_data))
        for idx, (date, activities) in enumerate(calendar_data.items()):
            with cols[idx]:
                st.markdown(f"##### 📅 {date}")
                for act in activities:
                    with st.container(border=True):
                        st.write(f"**🕒 {act['activity_time']}**")
                        st.write(act['activity'])
                        if st.button("❌", key=f"del_act_{act['id']}"):
                            conn = get_db()
                            with conn.cursor() as cur:
                                cur.execute('DELETE FROM itinerary WHERE id = %s', (act['id'],))
                                conn.commit()
                            conn.close()
                            st.rerun()
    else:
        st.info("Noch keine Aktivitäten geplant.")
        
    st.markdown("---")
    
# 📝 TO-DOS & 🎒 PACKLISTE
    col_todo, col_pack = st.columns(2)
    
    # Datenbank neu abfragen, um die user_id bei den Todos zu haben
    conn = get_db()
    with conn.cursor() as cur:
        # Echte To-Dos: Alle sehen alle Aufgaben für diesen Trip
        cur.execute('''
            SELECT t.*, u.username as helper 
            FROM todos t 
            LEFT JOIN users u ON t.user_id = u.id 
            WHERE t.trip_id = %s AND t.type = 'task'
        ''', (trip_id,))
        todos = cur.fetchall()
        
        # Packliste: Man sieht NUR die eigenen Sachen, die man selbst erstellt hat
        cur.execute('SELECT * FROM todos WHERE trip_id = %s AND type = \'pack\' AND user_id = %s', (trip_id, user_id))
        packing_list = cur.fetchall()
    conn.close()
    
    with col_todo:
        st.header("📝 Gemeinsame To-Dos")
        todo_task = st.text_input("Neues To-Do", key="todo_input")
        if st.button("Hinzufügen", key="todo_btn") and todo_task:
            conn = get_db()
            with conn.cursor() as cur:
                # Gemeinsame Aufgabe: user_id bleibt beim Erstellen leer oder unverknüpft für den Status
                cur.execute('INSERT INTO todos (trip_id, task, type, done) VALUES (%s, %s, \'task\', 0)', (trip_id, todo_task))
                conn.commit()
            conn.close()
            st.rerun()
            
        for todo in todos:
            # Info-Text, wer es erledigt hat
            status_text = f" (Erledigt von: {todo['helper']})" if todo['done'] and todo['helper'] else ""
            checked = st.checkbox(f"{todo['task']}{status_text}", value=bool(todo['done']), key=f"todo_{todo['id']}")
            
            if checked != bool(todo['done']):
                conn = get_db()
                with conn.cursor() as cur:
                    # Wenn abgehakt, tragen wir die ID des aktuellen Users ein, sonst löschen wir sie wieder
                    new_user = user_id if checked else None
                    cur.execute('UPDATE todos SET done = %s, user_id = %s WHERE id = %s', (1 if checked else 0, new_user, todo['id']))
                    conn.commit()
                conn.close()
                st.rerun()
                
    with col_pack:
        st.header("🎒 Meine persönliche Packliste")
        pack_task = st.text_input("Neues Packlisten-Item", key="pack_input")
        if st.button("Hinzufügen", key="pack_btn") and pack_task:
            conn = get_db()
            with conn.cursor() as cur:
                # Hier verknüpfen wir das Item fest mit deiner user_id!
                cur.execute('INSERT INTO todos (trip_id, task, type, user_id, done) VALUES (%s, %s, \'pack\', %s, 0)', (trip_id, pack_task, user_id))
                conn.commit()
            conn.close()
            st.rerun()
            
        for item in packing_list:
            checked = st.checkbox(item['task'], value=bool(item['done']), key=f"pack_{item['id']}")
            if checked != bool(item['done']):
                conn = get_db()
                with conn.cursor() as cur:
                    cur.execute('UPDATE todos SET done = %s WHERE id = %s', (1 if checked else 0, item['id']))
                    conn.commit()
                conn.close()
                st.rerun()

    # 💰 AUSGABEN & 📌 NOTIZEN
    col_exp, col_notes = st.columns(2)
    with col_exp:
        st.header("💰 Ausgaben-Tracker")
        total_expenses = sum(exp['amount'] for exp in expenses)
        st.subheader(f"Gesamtausgaben bisher: :red[{total_expenses:.2f} €]")
        
        with st.form("add_expense_form"):
            amount = st.number_input("Betrag (€)", min_value=0.0, step=0.01)
            category = st.selectbox("Kategorie", ["Transport", "Unterkunft", "Verpflegung", "Aktivitäten"])
            description = st.text_input("Notiz (z.B. Hostel Rom)")
            submit_exp = st.form_submit_button("Eintrag speichern")
            
            if submit_exp and amount:
                conn = get_db()
                with conn.cursor() as cur:
                    cur.execute('INSERT INTO expenses (trip_id, amount, category, description) VALUES (%s, %s, %s, %s)', 
                                (trip_id, amount, category, description))
                    conn.commit()
                conn.close()
                st.rerun()
                
        for exp in expenses:
            with st.container():
                st.write(f"**{exp['amount']:.2f} €** | *{exp['category']}* | {exp['description']}")
                if st.button("Ausgabe löschen ❌", key=f"del_exp_{exp['id']}"):
                    conn = get_db()
                    with conn.cursor() as cur:
                        cur.execute('DELETE FROM expenses WHERE id = %s', (exp['id'],))
                        conn.commit()
                    conn.close()
                    st.rerun()

    with col_notes:
        st.header("📌 Wichtige Notizen & Infos")
        notes_text = st.text_area("Hier ist Platz für Buchungsnummern, Hotel-Adressen etc.", value=trip['notes'] or '', height=250)
        if st.button("Notizen speichern 💾"):
            conn = get_db()
            with conn.cursor() as cur:
                cur.execute('UPDATE trips SET notes = %s WHERE id = %s', (notes_text, trip_id))
                conn.commit()
            conn.close()
            st.success("Notizen aktualisiert!")

# --- ROUTING LOGIK ---
if not st.session_state["logged_in"]:
    show_login()
else:
    with st.sidebar:
        st.write(f"👤 Account: **{st.session_state['username']}**")
        if st.button("Abmelden 🚪"):
            st.session_state["logged_in"] = False
            st.session_state["user_id"] = None
            st.session_state["username"] = ""
            st.session_state["current_trip_id"] = None
            st.rerun()

    if st.session_state["current_trip_id"] is None:
        show_overview()
    else:
        show_detail(st.session_state["current_trip_id"])
