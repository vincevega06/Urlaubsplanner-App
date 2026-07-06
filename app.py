from flask import Flask, render_template, request, redirect
import sqlite3

app = Flask(__name__)

def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        # Haupttabelle für die Trips (bleibt gleich)
        conn.execute('''CREATE TABLE IF NOT EXISTS trips 
                        (id INTEGER PRIMARY KEY, title TEXT, destination TEXT, 
                         start_date TEXT, end_date TEXT, status TEXT)''')
        
        # Die Notizen-Spalte (hast du im Schritt davor schon eingebaut)
        try:
            conn.execute('ALTER TABLE trips ADD COLUMN notes TEXT DEFAULT ""')
        except sqlite3.OperationalError:
            pass
            
        # Die To-Do-Tabelle inklusive Typ (hast du auch schon)
        conn.execute('''CREATE TABLE IF NOT EXISTS todos 
                        (id INTEGER PRIMARY KEY, trip_id INTEGER, task TEXT, done INTEGER DEFAULT 0, type TEXT DEFAULT "task")''')
        
        # Die Ausgaben-Tabelle (bleibt gleich)
        conn.execute('''CREATE TABLE IF NOT EXISTS expenses 
                        (id INTEGER PRIMARY KEY, trip_id INTEGER, amount REAL, category TEXT, description TEXT)''')
        
        # NEU: Das fügst du jetzt neu hinzu für den Tagesplan
        conn.execute('''CREATE TABLE IF NOT EXISTS itinerary 
                        (id INTEGER PRIMARY KEY, trip_id INTEGER, 
                         activity_date TEXT, activity_time TEXT, activity TEXT)''')
init_db()

from datetime import datetime  # NEU: Ganz oben zu den Imports hinzufügen!

@app.route('/')
def index():
    conn = get_db()
    trips_raw = conn.execute('SELECT * FROM trips').fetchall()
    
    # Finanzen berechnen (bleibt gleich)
    all_expenses = conn.execute('SELECT amount, category FROM expenses').fetchall()
    total_all_trips = sum(exp['amount'] for exp in all_expenses)
    category_totals = {'Transport': 0.0, 'Unterkunft': 0.0, 'Verpflegung': 0.0, 'Aktivitäten': 0.0}
    for exp in all_expenses:
        if exp['category'] in category_totals:
            category_totals[exp['category']] += exp['amount']
            
    conn.close()
    
    # NEU: Countdown für jeden Trip berechnen
    trips = []
    today = datetime.now().date()
    
    for row in trips_raw:
        # Wir machen aus der Zeile ein beschreibbares Dictionary
        trip_dict = dict(row)
        
        try:
            # Das gespeicherte Datum (String) in ein Python-Datum umwandeln
            start_date = datetime.strptime(trip_dict['start_date'], '%Y-%m-%d').date()
            end_date = datetime.strptime(trip_dict['end_date'], '%Y-%m-%d').date()
            
            if today < start_date:
                # Trip liegt in der Zukunft
                days_left = (start_date - today).days
                trip_dict['countdown_text'] = f"⏳ Noch {days_left} Tage"
            elif start_date <= today <= end_date:
                # Man ist gerade im Urlaub
                trip_dict['countdown_text'] = "✈️ Aktuell im Urlaub! Gute Reise!"
            else:
                # Trip ist vorbei
                trip_dict['countdown_text'] = "✅ Vorbeigezogen"
        except (ValueError, TypeError):
            # Falls mal kein oder ein falsches Datum eingetragen wurde
            trip_dict['countdown_text'] = "Kein Datum verfügbar"
            
        trips.append(trip_dict)
    
    return render_template('index.html', 
                           trips=trips, 
                           total_all_trips=total_all_trips, 
                           category_totals=category_totals)

@app.route('/add', methods=['POST'])
def add_trip():
    with get_db() as conn:
        conn.execute('INSERT INTO trips (title, destination, start_date, end_date, status) VALUES (?, ?, ?, ?, ?)', 
                     (request.form['title'], request.form['destination'], request.form['start_date'], request.form['end_date'], request.form['status']))
    return redirect('/')

@app.route('/trip/<int:trip_id>')
def trip_detail(trip_id):
    conn = get_db()
    trip = conn.execute('SELECT * FROM trips WHERE id = ?', (trip_id,)).fetchone()
    todos = conn.execute('SELECT * FROM todos WHERE trip_id = ? AND type = "task"', (trip_id,)).fetchall()
    packing_list = conn.execute('SELECT * FROM todos WHERE trip_id = ? AND type = "pack"', (trip_id,)).fetchall()
    expenses = conn.execute('SELECT * FROM expenses WHERE trip_id = ?', (trip_id,)).fetchall()
    total_expenses = sum(exp['amount'] for exp in expenses)
    
    # Alle Aktivitäten holen
    itinerary_raw = conn.execute('SELECT * FROM itinerary WHERE trip_id = ? ORDER BY activity_date ASC, activity_time ASC', (trip_id,)).fetchall()
    
    # NEU: Aktivitäten nach Datum gruppieren für die Kalenderansicht
    calendar_data = {}
    for item in itinerary_raw:
        date_str = item['activity_date']
        if date_str not in calendar_data:
            calendar_data[date_str] = []
        calendar_data[date_str].append(item)
        
    conn.close()
    return render_template('detail.html', 
                           trip=trip, 
                           todos=todos, 
                           packing_list=packing_list, 
                           expenses=expenses, 
                           total_expenses=total_expenses, 
                           calendar_data=calendar_data) # Wir übergeben das neue Kalender-Dict
# NEU: Aktivität hinzufügen
@app.route('/trip/<int:trip_id>/add_activity', methods=['POST'])
def add_activity(trip_id):
    date = request.form['activity_date']
    time = request.form['activity_time']
    activity = request.form['activity']
    with get_db() as conn:
        conn.execute('INSERT INTO itinerary (trip_id, activity_date, activity_time, activity) VALUES (?, ?, ?, ?)', 
                     (trip_id, date, time, activity))
    return redirect(f'/trip/{trip_id}')

# NEU: Aktivität löschen
@app.route('/trip/<int:trip_id>/delete_activity/<int:activity_id>')
def delete_activity(trip_id, activity_id):
    with get_db() as conn:
        conn.execute('DELETE FROM itinerary WHERE id = ?', (activity_id,))
    return redirect(f'/trip/{trip_id}')

# UPDATE: Nimmt jetzt auch den Typen aus dem Formular entgegen
@app.route('/trip/<int:trip_id>/add_todo', methods=['POST'])
def add_todo(trip_id):
    task = request.form['task']
    item_type = request.form['type'] # 'task' oder 'pack'
    with get_db() as conn:
        conn.execute('INSERT INTO todos (trip_id, task, type) VALUES (?, ?, ?)', (trip_id, task, item_type))
    return redirect(f'/trip/{trip_id}')

@app.route('/trip/<int:trip_id>/toggle_todo/<int:todo_id>')
def toggle_todo(trip_id, todo_id):
    conn = get_db()
    current = conn.execute('SELECT done FROM todos WHERE id = ?', (todo_id,)).fetchone()
    new_status = 1 if current['done'] == 0 else 0
    conn.execute('UPDATE todos SET done = ? WHERE id = ?', (new_status, todo_id))
    conn.commit()
    conn.close()
    return redirect(f'/trip/{trip_id}')

@app.route('/trip/<int:trip_id>/add_expense', methods=['POST'])
def add_expense(trip_id):
    with get_db() as conn:
        conn.execute('INSERT INTO expenses (trip_id, amount, category, description) VALUES (?, ?, ?, ?)', 
                     (trip_id, float(request.form['amount']), request.form['category'], request.form['description']))
    return redirect(f'/trip/{trip_id}')

@app.route('/trip/<int:trip_id>/delete_expense/<int:expense_id>')
def delete_expense(trip_id, expense_id):
    with get_db() as conn:
        conn.execute('DELETE FROM expenses WHERE id = ?', (expense_id,))
    return redirect(f'/trip/{trip_id}')

@app.route('/trip/<int:trip_id>/delete')
def delete_trip(trip_id):
    with get_db() as conn:
        conn.execute('DELETE FROM trips WHERE id = ?', (trip_id,))
        conn.execute('DELETE FROM todos WHERE trip_id = ?', (trip_id,))
        conn.execute('DELETE FROM expenses WHERE trip_id = ?', (trip_id,))
    return redirect('/')

@app.route('/trip/<int:trip_id>/save_notes', methods=['POST'])
def save_notes(trip_id):
    notes = request.form['notes']
    with get_db() as conn:
        conn.execute('UPDATE trips SET notes = ? WHERE id = ?', (notes, trip_id))
    return redirect(f'/trip/{trip_id}')

if __name__ == '__main__':
    app.run(debug=True)