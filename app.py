from flask import Flask, render_template, request, redirect
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)

# CHANGER: Hier fügst du deine kopierte URI von Supabase ein!
DATABASE_URL ="postgresql://postgres.qyqsyppkuakmmwzrjsft:vasgig7fixcypuKsyg@aws-1-eu-west-2.pooler.supabase.com:6543/postgres"

def get_db():
    # Verbindet sich direkt mit der Cloud-Datenbank
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

# Initialisierung der Cloud-Datenbank
def init_db():
    conn = get_db()
    with conn.cursor() as cur:
        # 1. Haupttabelle für Trips
        cur.execute('''CREATE TABLE IF NOT EXISTS trips 
                       (id SERIAL PRIMARY KEY, title TEXT, destination TEXT, 
                        start_date TEXT, end_date TEXT, status TEXT, notes TEXT DEFAULT '')''')
        
        # 2. Tabelle für To-Dos & Packlisten
        cur.execute('''CREATE TABLE IF NOT EXISTS todos 
                       (id SERIAL PRIMARY KEY, trip_id INTEGER, task TEXT, done INTEGER DEFAULT 0, type TEXT DEFAULT 'task')''')
        
        # 3. Tabelle für Ausgaben
        cur.execute('''CREATE TABLE IF NOT EXISTS expenses 
                       (id SERIAL PRIMARY KEY, trip_id INTEGER, amount REAL, category TEXT, description TEXT)''')
        
        # 4. Tabelle für den Kalender / Zeitplan
        cur.execute('''CREATE TABLE IF NOT EXISTS itinerary 
                       (id SERIAL PRIMARY KEY, trip_id INTEGER, activity_date TEXT, activity_time TEXT, activity TEXT)''')
        
        conn.commit()
    conn.close()

init_db()

@app.route('/')
def index():
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('SELECT * FROM trips')
        trips_raw = cur.fetchall()
        cur.execute('SELECT amount, category FROM expenses')
        all_expenses = cur.fetchall()
    conn.close()
    
    total_all_trips = sum(exp['amount'] for exp in all_expenses)
    category_totals = {'Transport': 0.0, 'Unterkunft': 0.0, 'Verpflegung': 0.0, 'Aktivitäten': 0.0}
    for exp in all_expenses:
        if exp['category'] in category_totals:
            category_totals[exp['category']] += exp['amount']
            
    trips = []
    today = datetime.now().date()
    for row in trips_raw:
        trip_dict = dict(row)
        try:
            start_date = datetime.strptime(trip_dict['start_date'], '%Y-%m-%d').date()
            end_date = datetime.strptime(trip_dict['end_date'], '%Y-%m-%d').date()
            if today < start_date:
                trip_dict['countdown_text'] = f"⏳ Noch {(start_date - today).days} Tage"
            elif start_date <= today <= end_date:
                trip_dict['countdown_text'] = "✈️ Aktuell im Urlaub!"
            else:
                trip_dict['countdown_text'] = "✅ Vorbeigezogen"
        except:
            trip_dict['countdown_text'] = "Kein Datum"
        trips.append(trip_dict)
    
    return render_template('index.html', trips=trips, total_all_trips=total_all_trips, category_totals=category_totals)

@app.route('/add', methods=['POST'])
def add_trip():
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('INSERT INTO trips (title, destination, start_date, end_date, status) VALUES (%s, %s, %s, %s, %s)', 
                    (request.form['title'], request.form['destination'], request.form['start_date'], request.form['end_date'], request.form['status']))
        conn.commit()
    conn.close()
    return redirect('/')

@app.route('/trip/<int:trip_id>')
def trip_detail(trip_id):
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
    conn.close()
    
    total_expenses = sum(exp['amount'] for exp in expenses)
    calendar_data = {}
    for item in itinerary_raw:
        date_str = item['activity_date']
        if date_str not in calendar_data:
            calendar_data[date_str] = []
        calendar_data[date_str].append(item)
        
    return render_template('detail.html', trip=trip, todos=todos, packing_list=packing_list, expenses=expenses, total_expenses=total_expenses, calendar_data=calendar_data)

@app.route('/trip/<int:trip_id>/add_todo', methods=['POST'])
def add_todo(trip_id):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('INSERT INTO todos (trip_id, task, type) VALUES (%s, %s, %s)', (trip_id, request.form['task'], request.form['type']))
        conn.commit()
    conn.close()
    return redirect(f'/trip/{trip_id}')

@app.route('/trip/<int:trip_id>/toggle_todo/<int:todo_id>')
def toggle_todo(trip_id, todo_id):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('SELECT done FROM todos WHERE id = %s', (todo_id,))
        current = cur.fetchone()
        new_status = 1 if current['done'] == 0 else 0
        cur.execute('UPDATE todos SET done = %s WHERE id = %s', (new_status, todo_id))
        conn.commit()
    conn.close()
    return redirect(f'/trip/{trip_id}')

@app.route('/trip/<int:trip_id>/add_expense', methods=['POST'])
def add_expense(trip_id):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('INSERT INTO expenses (trip_id, amount, category, description) VALUES (%s, %s, %s, %s)', 
                    (trip_id, float(request.form['amount']), request.form['category'], request.form['description']))
        conn.commit()
    conn.close()
    return redirect(f'/trip/{trip_id}')

@app.route('/trip/<int:trip_id>/delete_expense/<int:expense_id>')
def delete_expense(trip_id, expense_id):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('DELETE FROM expenses WHERE id = %s', (expense_id,))
        conn.commit()
    conn.close()
    return redirect(f'/trip/{trip_id}')

@app.route('/trip/<int:trip_id>/add_activity', methods=['POST'])
def add_activity(trip_id):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('INSERT INTO itinerary (trip_id, activity_date, activity_time, activity) VALUES (%s, %s, %s, %s)', 
                    (trip_id, request.form['activity_date'], request.form['activity_time'], request.form['activity']))
        conn.commit()
    conn.close()
    return redirect(f'/trip/{trip_id}')

@app.route('/trip/<int:trip_id>/delete_activity/<int:activity_id>')
def delete_activity(trip_id, activity_id):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('DELETE FROM itinerary WHERE id = %s', (activity_id,))
        conn.commit()
    conn.close()
    return redirect(f'/trip/{trip_id}')

@app.route('/trip/<int:trip_id>/save_notes', methods=['POST'])
def save_notes(trip_id):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('UPDATE trips SET notes = %s WHERE id = %s', (request.form['notes'], trip_id))
        conn.commit()
    conn.close()
    return redirect(f'/trip/{trip_id}')

@app.route('/trip/<int:trip_id>/delete')
def delete_trip(trip_id):
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute('DELETE FROM trips WHERE id = %s', (trip_id,))
        cur.execute('DELETE FROM todos WHERE trip_id = %s', (trip_id,))
        cur.execute('DELETE FROM expenses WHERE trip_id = %s', (trip_id,))
        cur.execute('DELETE FROM itinerary WHERE trip_id = %s', (trip_id,))
        conn.commit()
    conn.close()
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)
