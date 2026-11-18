from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify, Response
from datetime import datetime, date
import sqlite3, math, io, base64, csv, json
import qrcode

app = Flask(__name__)
app.secret_key = 'nyewasco_2026'

def init_db():
    conn = sqlite3.connect('nyewasco.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY, staff_number TEXT UNIQUE, name TEXT, password TEXT,
        department TEXT, station TEXT, station_lat REAL, station_lon REAL,
        geofence_radius INTEGER DEFAULT 500, qr_code TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY, employee_id INTEGER, date TEXT,
        clock_in_time TEXT, clock_out_time TEXT, clock_in_lat REAL, clock_in_lon REAL,
        geofence_status TEXT, distance_meters REAL, location_source TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS leave_requests (
        id INTEGER PRIMARY KEY, employee_id INTEGER, leave_type TEXT, start_date TEXT, 
        end_date TEXT, reason TEXT, status TEXT DEFAULT 'PENDING', created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY, user TEXT, action TEXT, details TEXT, timestamp TEXT)''')
    
    for emp in [('NYE001','John Doe','IT Department','Head Office',-0.4197,36.9522,500),
                ('NYE002','Jane Smith','HR Department','Head Office',-0.4197,36.9522,500),
                ('NYE003','Peter Kamau','Operations','Treatment Plant',-0.4250,36.9600,300)]:
        c.execute("SELECT id FROM employees WHERE staff_number=?", (emp[0],))
        if not c.fetchone():
            qr = qrcode.QRCode(box_size=8, border=4)
            qr.add_data(f'NYEWASCO:{emp[0]}')
            qr.make(fit=True)
            buf = io.BytesIO()
            qr.make_image().save(buf, format='PNG')
            c.execute("INSERT INTO employees (staff_number,name,password,department,station,station_lat,station_lon,geofence_radius,qr_code) VALUES (?,?,?,?,?,?,?,?,?)",
                      (emp[0],emp[1],'password',emp[2],emp[3],emp[4],emp[5],emp[6],base64.b64encode(buf.getvalue()).decode()))
    conn.commit(); conn.close()

def log_audit(user, action, details=""):
    conn = sqlite3.connect('nyewasco.db'); c = conn.cursor()
    c.execute("INSERT INTO audit_logs (user, action, details, timestamp) VALUES (?,?,?,?)",
              (user, action, details, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit(); conn.close()

BASE = '''<!DOCTYPE html><html><head><title>NYEWASCO Smart Attendance</title>
<script src="https://cdn.tailwindcss.com"></script>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
<style>
.grad{background:linear-gradient(135deg,#0f172a,#1e3a8a)}#map{height:380px;border-radius:12px}
.radar{width:100px;height:100px;border-radius:50%;border:2px solid #3b82f6;position:relative;margin:0 auto;animation:pulse 2s infinite}
.radar::before{content:'';position:absolute;top:50%;left:50%;width:50%;height:50%;background:rgba(59,130,246,0.5);transform-origin:0 0;animation:scan 2s linear infinite}
@keyframes scan{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(59,130,246,0.7)}70%{box-shadow:0 0 0 20px rgba(59,130,246,0)}100%{box-shadow:0 0 0 0 rgba(59,130,246,0)}}
</style></head><body class="bg-gray-100 min-h-screen">'''

LOGIN = BASE + '''
<div class="grad min-h-screen flex items-center justify-center"><div class="bg-white p-10 rounded-2xl shadow-2xl w-96">
<div class="text-center mb-6"><div class="w-16 h-16 bg-blue-700 rounded-full mx-auto flex items-center justify-center"><i class="fas fa-tint text-white text-2xl"></i></div>
<h1 class="text-2xl font-bold mt-4">NYEWASCO</h1><p class="text-gray-500">Smart Attendance System</p></div>
{% if error %}<p class="text-red-600 text-center mb-3">{{ error }}</p>{% endif %}
<form method="POST" action="/login">
<input name="staff_number" value="NYE001" class="w-full p-3 border rounded-lg mb-3" placeholder="Staff Number">
<input name="password" value="password" type="password" class="w-full p-3 border rounded-lg mb-5" placeholder="Password">
<button class="w-full bg-blue-700 text-white p-3 rounded-lg font-bold hover:bg-blue-800">Log In</button></form>
<p class="text-xs text-gray-400 text-center mt-4">NYE001 / NYE002 / NYE003 — password: password</p>
</div></div></body></html>'''

DASH = BASE + '''
<div class="max-w-6xl mx-auto p-4">
<div class="grad text-white p-6 rounded-2xl shadow-lg mb-6 flex justify-between items-center">
<div><h2 class="text-2xl font-bold">Welcome, {{ employee.name }}</h2>
<p class="text-blue-200 text-sm mt-1">{{ employee.staff_number }} | {{ employee.department }} | {{ employee.station }}</p></div>
<div class="flex gap-2">
<a href="/supervisor" class="bg-white/20 px-4 py-2 rounded-lg text-sm font-bold hover:bg-white/30"><i class="fas fa-users mr-1"></i>Supervisor</a>
<button onclick="openLeaveModal()" class="bg-yellow-500/80 px-4 py-2 rounded-lg text-sm font-bold hover:bg-yellow-500"><i class="fas fa-plane mr-1"></i>Request Leave</button>
<a href="/logout" class="bg-red-500 px-4 py-2 rounded-lg text-sm font-bold hover:bg-red-600">Logout</a></div></div>

<div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
<div class="bg-white p-6 rounded-2xl shadow">
<h3 class="font-bold text-lg mb-4"><i class="fas fa-clock text-blue-600 mr-2"></i>Today</h3>
{% if today_record %}
<div class="bg-blue-50 p-4 rounded-xl mb-4 text-sm">
<p><b class="text-green-600">In:</b> {{ today_record.clock_in_time }} &nbsp; <span class="text-gray-500">({{ today_record.location_source }})</span></p>
{% if today_record.clock_out_time %}<p class="mt-1"><b class="text-red-600">Out:</b> {{ today_record.clock_out_time }}</p>{% endif %}
<p class="mt-1">Distance: {{ "%.0f"|format(today_record.distance_meters) }}m from station</p>
<p class="mt-1 font-bold {% if today_record.geofence_status=='PASS' %}text-green-600{% else %}text-red-600{% endif %}">Geofence: {{ today_record.geofence_status }}</p></div>
{% if not today_record.clock_out_time %}
<button onclick="doClock('out')" class="w-full bg-red-600 text-white font-bold py-4 rounded-xl hover:bg-red-700"><i class="fas fa-sign-out-alt mr-2"></i>CLOCK OUT</button>
{% else %}<p class="text-green-600 font-bold text-center py-4"><i class="fas fa-check-circle mr-2"></i>Shift complete</p>{% endif %}
{% else %}
<p class="text-gray-500 mb-4 text-center">Tap the button or use your voice to clock in.</p>
<div class="flex gap-3">
<button onclick="doClock('in')" class="flex-1 bg-green-600 text-white font-bold py-4 rounded-xl hover:bg-green-700"><i class="fas fa-fingerprint mr-2"></i>CLOCK IN</button>
<button onclick="startVoice()" class="w-16 bg-purple-600 text-white font-bold py-4 rounded-xl hover:bg-purple-700 flex items-center justify-center"><i class="fas fa-microphone text-xl"></i></button>
</div>
{% endif %}
<div id="radarBox" class="hidden mt-4 text-center"><div class="radar"></div><p class="text-sm text-blue-600 mt-2">Acquiring GPS & Verifying Location...</p></div>
<p id="msg" class="text-center text-sm text-blue-600 mt-3"></p></div>

<div class="bg-white p-6 rounded-2xl shadow text-center">
<h3 class="font-bold text-lg mb-4"><i class="fas fa-qrcode text-purple-600 mr-2"></i>My QR Badge</h3>
<img src="data:image/png;base64,{{ employee.qr_code }}" class="mx-auto border-4 border-purple-100 rounded-lg w-48">
<p class="text-xs text-gray-500 mt-3">{{ employee.staff_number }} — scan at site entrance</p>
<button onclick="fetchAudit()" class="mt-4 text-xs text-gray-400 underline">View My Audit Trail</button></div></div>

<div class="bg-white p-6 rounded-2xl shadow mb-6">
<h3 class="font-bold text-lg mb-4"><i class="fas fa-map-marked-alt text-green-600 mr-2"></i>{{ employee.station }} — Geofence Zone</h3>
<div id="map"></div></div>

<div class="bg-white p-6 rounded-2xl shadow">
<h3 class="font-bold text-lg mb-4"><i class="fas fa-history text-indigo-600 mr-2"></i>History</h3>
<table class="w-full text-sm"><thead class="bg-gray-50"><tr><th class="p-3 text-left">Date</th><th class="p-3 text-left">In</th><th class="p-3 text-left">Out</th><th class="p-3 text-left">Geofence</th></tr></thead>
<tbody>{% for r in recent %}<tr class="border-t"><td class="p-3">{{ r.date }}</td><td class="p-3">{{ r.clock_in_time }}</td><td class="p-3">{{ r.clock_out_time or '-' }}</td>
<td class="p-3 font-bold {% if r.geofence_status=='PASS' %}text-green-600{% else %}text-red-600{% endif %}">{{ r.geofence_status }}</td></tr>{% endfor %}</tbody></table>
<a href="/reset-demo" class="text-xs text-gray-400 mt-3 inline-block">Reset today's records (demo)</a></div></div>

<!-- Leave Modal -->
<div id="leaveModal" class="hidden fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
<div class="bg-white p-6 rounded-2xl w-96">
<h3 class="font-bold text-lg mb-4">Request Leave</h3>
<select id="leaveType" class="w-full p-2 border rounded mb-3"><option>Annual</option><option>Sick</option><option>Compassionate</option></select>
<input type="date" id="leaveStart" class="w-full p-2 border rounded mb-3">
<textarea id="leaveReason" placeholder="Reason" class="w-full p-2 border rounded mb-4"></textarea>
<div class="flex gap-2"><button onclick="submitLeave()" class="flex-1 bg-blue-600 text-white py-2 rounded">Submit</button>
<button onclick="document.getElementById('leaveModal').classList.add('hidden')" class="flex-1 bg-gray-300 py-2 rounded">Cancel</button></div></div></div>

<!-- Audit Modal -->
<div id="auditModal" class="hidden fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
<div class="bg-white p-6 rounded-2xl w-[500px] max-h-[80vh] overflow-y-auto">
<h3 class="font-bold text-lg mb-4">Immutable Audit Trail (FR-38)</h3>
<div id="auditContent" class="text-sm space-y-2"></div>
<button onclick="document.getElementById('auditModal').classList.add('hidden')" class="mt-4 w-full bg-gray-300 py-2 rounded">Close</button></div></div>

<script>
const SLAT={{ employee.station_lat }}, SLON={{ employee.station_lon }};
const map=L.map('map').setView([SLAT,SLON],15);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);
L.circle([SLAT,SLON],{radius:{{ employee.geofence_radius }},color:'#2563eb',fillOpacity:0.15}).addTo(map).bindPopup('Geofence: {{ employee.geofence_radius }}m');
L.marker([SLAT,SLON]).addTo(map).bindPopup('<b>{{ employee.station }}</b>');

function doClock(a){
  document.getElementById('radarBox').classList.remove('hidden');
  if(navigator.geolocation){
    navigator.geolocation.getCurrentPosition(
      p=>send(a,p.coords.latitude,p.coords.longitude,'GPS'),
      e=>send(a,SLAT,SLON,'STATION'),{timeout:6000});
  } else send(a,SLAT,SLON,'STATION');
}
function send(a,lat,lon,src){
  fetch('/clock-'+a,{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({lat:lat,lon:lon,src:src})})
  .then(r=>r.json()).then(d=>{ if(d.error){document.getElementById('msg').innerText=d.error;} else location.reload(); });
}

function startVoice() {
  if (!('webkitSpeechRecognition' in window)) { alert('Voice not supported in this browser.'); return; }
  const recognition = new webkitSpeechRecognition();
  recognition.lang = 'en-US';
  recognition.start();
  document.getElementById('msg').innerText = '🎙️ Listening... Say "Clock In"';
  recognition.onresult = function(event) {
    const transcript = event.results[0][0].transcript.toLowerCase();
    if (transcript.includes('clock in') || transcript.includes('clock')) {
      doClock('in');
    } else {
      document.getElementById('msg').innerText = 'Did not understand. Try again.';
    }
  };
}

function openLeaveModal() { document.getElementById('leaveModal').classList.remove('hidden'); }
function submitLeave() {
  fetch('/request-leave', {method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({type:document.getElementById('leaveType').value, start:document.getElementById('leaveStart').value, reason:document.getElementById('leaveReason').value})})
  .then(()=>{alert('Leave request sent to supervisor!'); location.reload();});
}

function fetchAudit() {
  fetch('/get-audit').then(r=>r.json()).then(data=>{
    let html = '';
    data.forEach(l => html += `<div class="border-b pb-2"><b>${l.timestamp}</b> - ${l.action}<br><span class="text-gray-500">${l.details}</span></div>`);
    document.getElementById('auditContent').innerHTML = html;
    document.getElementById('auditModal').classList.remove('hidden');
  });
}
</script></body></html>'''

SUP = BASE + '''
<div class="max-w-6xl mx-auto p-4">
<div class="grad text-white p-6 rounded-2xl shadow-lg mb-6 flex justify-between items-center">
<h2 class="text-2xl font-bold"><i class="fas fa-users mr-2"></i>Supervisor Dashboard</h2>
<div class="flex gap-2">
    <a href="/export-csv" class="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg text-sm font-bold"><i class="fas fa-file-csv mr-2"></i>Export CSV</a>
    <a href="/" class="bg-white/20 px-4 py-2 rounded-lg text-sm font-bold hover:bg-white/30">Back</a>
</div></div>
<div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
<div class="bg-white p-5 rounded-xl shadow text-center"><p class="text-3xl font-bold text-blue-600">{{ stats.total }}</p><p class="text-xs text-gray-500">Staff</p></div>
<div class="bg-white p-5 rounded-xl shadow text-center"><p class="text-3xl font-bold text-green-600">{{ stats.present }}</p><p class="text-xs text-gray-500">Present</p></div>
<div class="bg-white p-5 rounded-xl shadow text-center"><p class="text-3xl font-bold text-yellow-600">{{ stats.late }}</p><p class="text-xs text-gray-500">Late</p></div>
<div class="bg-white p-5 rounded-xl shadow text-center"><p class="text-3xl font-bold text-red-600">{{ stats.absent }}</p><p class="text-xs text-gray-500">Absent</p></div></div>
<div class="bg-white p-6 rounded-2xl shadow mb-6"><h3 class="font-bold mb-3"><i class="fas fa-map-pin text-green-600 mr-2"></i>Live Clock-In Locations</h3><div id="smap"></div></div>
<div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
<div class="bg-white p-6 rounded-2xl shadow"><table class="w-full text-sm"><thead class="bg-gray-50"><tr><th class="p-3 text-left">Staff</th><th class="p-3 text-left">In</th><th class="p-3 text-left">Status</th><th class="p-3 text-left">Geofence</th></tr></thead>
<tbody>{% for r in records %}<tr class="border-t"><td class="p-3 font-semibold">{{ r.name }}</td><td class="p-3">{{ r.clock_in_time }}</td>
<td class="p-3">{% if r.is_late %}<span class="bg-yellow-100 text-yellow-700 px-2 py-1 rounded-full text-xs font-bold">LATE</span>{% else %}<span class="bg-green-100 text-green-700 px-2 py-1 rounded-full text-xs font-bold">ON TIME</span>{% endif %}</td>
<td class="p-3 font-bold {% if r.geofence_status=='PASS' %}text-green-600{% else %}text-red-600{% endif %}">{{ r.geofence_status }}</td></tr>{% endfor %}</tbody></table></div>
<div class="bg-white p-6 rounded-2xl shadow"><h3 class="font-bold mb-3"><i class="fas fa-shield-alt text-indigo-600 mr-2"></i>Live Audit Feed (FR-38)</h3>
<div id="liveAudit" class="h-64 overflow-y-auto text-sm space-y-2"></div></div></div></div>
<script>
const smap=L.map('smap').setView([-0.4197,36.9522],13);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(smap);
{% for r in records %}{% if r.clock_in_lat %}L.circleMarker([{{ r.clock_in_lat }},{{ r.clock_in_lon }}],{radius:8,color:'{{ '#16a34a' if r.geofence_status=='PASS' else '#dc2626' }}',fillOpacity:0.9}).addTo(smap).bindPopup('<b>{{ r.name }}</b><br>{{ r.clock_in_time }}');{% endif %}{% endfor %}
fetch('/get-audit').then(r=>r.json()).then(data=>{
  let html=''; data.forEach(l=>html+=`<div class="border-b pb-2"><b class="text-gray-500">${l.timestamp}</b><br>${l.user}: ${l.action} <i class="text-blue-500">${l.details}</i></div>`);
  document.getElementById('liveAudit').innerHTML=html;
});
</script></body></html>'''

@app.route('/')
def index():
    if not session.get('sn'): return render_template_string(LOGIN, error=None)
    conn = sqlite3.connect('nyewasco.db'); conn.row_factory = sqlite3.Row; c = conn.cursor()
    emp = c.execute("SELECT * FROM employees WHERE staff_number=?", (session['sn'],)).fetchone()
    if not emp: session.clear(); conn.close(); return redirect('/')
    today = date.today().isoformat()
    rec = c.execute("SELECT * FROM attendance WHERE employee_id=? AND date=?", (emp['id'], today)).fetchone()
    recent = c.execute("SELECT * FROM attendance WHERE employee_id=? ORDER BY date DESC LIMIT 10", (emp['id'],)).fetchall()
    conn.close()
    return render_template_string(DASH, employee=emp, today_record=rec, recent=recent)

@app.route('/supervisor')
def supervisor():
    if not session.get('sn'): return redirect('/')
    conn = sqlite3.connect('nyewasco.db'); conn.row_factory = sqlite3.Row; c = conn.cursor()
    today = date.today().isoformat()
    total = c.execute("SELECT COUNT(*) n FROM employees").fetchone()['n']
    rows = c.execute("""SELECT e.name, e.department, a.* FROM attendance a JOIN employees e ON a.employee_id = e.id WHERE a.date=?""", (today,)).fetchall()
    records = [dict(r) for r in rows]
    for r in records: r['is_late'] = (r['clock_in_time'] or '') > '08:10:00'
    present = len(records); late = sum(1 for r in records if r['is_late'])
    conn.close()
    return render_template_string(SUP, records=records, stats={'total': total, 'present': present, 'late': late, 'absent': total - present})

@app.route('/get-audit')
def get_audit():
    if not session.get('sn'): return jsonify([])
    conn = sqlite3.connect('nyewasco.db'); conn.row_factory = sqlite3.Row; c = conn.cursor()
    logs = c.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 50").fetchall()
    conn.close()
    return jsonify([dict(l) for l in logs])

@app.route('/request-leave', methods=['POST'])
def request_leave():
    if not session.get('sn'): return jsonify(error='Not logged in')
    d = request.get_json()
    conn = sqlite3.connect('nyewasco.db'); c = conn.cursor()
    emp = c.execute("SELECT id FROM employees WHERE staff_number=?", (session['sn'],)).fetchone()
    c.execute("INSERT INTO leave_requests (employee_id, leave_type, start_date, reason, status, created_at) VALUES (?,?,?,?,?,?)",
              (emp[0], d['type'], d['start'], d['reason'], 'PENDING', datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    log_audit(session['sn'], 'LEAVE_REQUEST', f"Type: {d['type']}, Start: {d['start']}")
    conn.commit(); conn.close()
    return jsonify(success=True)

@app.route('/export-csv')
def export_csv():
    if not session.get('sn'): return redirect('/')
    conn = sqlite3.connect('nyewasco.db'); conn.row_factory = sqlite3.Row; c = conn.cursor()
    c.execute("""SELECT e.staff_number, e.name, e.department, a.date, a.clock_in_time, a.clock_out_time, 
                        a.clock_in_lat, a.clock_in_lon, a.geofence_status, a.location_source
                 FROM attendance a JOIN employees e ON a.employee_id = e.id ORDER BY a.date DESC""")
    rows = c.fetchall(); conn.close()
    si = io.StringIO(); cw = csv.writer(si)
    cw.writerow(['Staff Number', 'Name', 'Department', 'Date', 'Clock In', 'Clock Out', 'Lat', 'Lon', 'Geofence', 'Source'])
    for row in rows: cw.writerow([row['staff_number'], row['name'], row['department'], row['date'], row['clock_in_time'] or 'N/A', row['clock_out_time'] or 'N/A', row['clock_in_lat'], row['clock_in_lon'], row['geofence_status'], row['location_source']])
    return Response(si.getvalue(), mimetype="text/csv", headers={"Content-disposition": "attachment; filename=nyewasco_report.csv"})

@app.route('/login', methods=['POST'])
def login():
    conn = sqlite3.connect('nyewasco.db'); c = conn.cursor()
    e = c.execute("SELECT * FROM employees WHERE staff_number=? AND password=?", (request.form['staff_number'], request.form['password'])).fetchone()
    conn.close()
    if e: 
        session['sn'] = e[1]; log_audit(e[1], 'LOGIN', 'User logged into system')
        return redirect('/')
    return render_template_string(LOGIN, error='Invalid credentials')

@app.route('/logout')
def logout(): 
    if session.get('sn'): log_audit(session['sn'], 'LOGOUT', 'User logged out')
    session.clear(); return redirect('/')

@app.route('/reset-demo')
def reset():
    conn = sqlite3.connect('nyewasco.db'); c = conn.cursor()
    c.execute("DELETE FROM attendance WHERE date=?", (date.today().isoformat(),)); conn.commit(); conn.close()
    return redirect('/')

def dist(a, b, x, y):
    R = 6371e3; p1, p2 = math.radians(float(a)), math.radians(float(x))
    h = math.sin((float(x) - float(a)) * math.pi / 360)**2 + math.cos(p1) * math.cos(p2) * math.sin((float(y) - float(b)) * math.pi / 360)**2
    return R * 2 * math.atan2(math.sqrt(h), math.sqrt(1 - h))

@app.route('/clock-in', methods=['POST'])
def cin():
    if not session.get('sn'): return jsonify(error='Not logged in')
    d = request.get_json(); conn = sqlite3.connect('nyewasco.db'); c = conn.cursor()
    e = c.execute("SELECT * FROM employees WHERE staff_number=?", (session['sn'],)).fetchone()
    if not e: conn.close(); return jsonify(error='User not found')
    today = date.today().isoformat()
    if c.execute("SELECT id FROM attendance WHERE employee_id=? AND date=?", (e[0], today)).fetchone():
        conn.close(); return jsonify(error='Already clocked in today')
    m = dist(float(e[6]), float(e[7]), float(d['lat']), float(d['lon']))
    c.execute("INSERT INTO attendance (employee_id, date, clock_in_time, clock_in_lat, clock_in_lon, geofence_status, distance_meters, location_source) VALUES (?,?,?,?,?,?,?,?)",
        (e[0], today, datetime.now().strftime('%H:%M:%S'), float(d['lat']), float(d['lon']), 'PASS' if m <= float(e[8]) else 'FAIL', m, d.get('src', 'UNKNOWN')))
    log_audit(session['sn'], 'CLOCK_IN', f"Source: {d.get('src')}, Dist: {m:.0f}m, Status: {'PASS' if m <= float(e[8]) else 'FAIL'}")
    conn.commit(); conn.close(); return jsonify(success=True)

@app.route('/clock-out', methods=['POST'])
def cout():
    if not session.get('sn'): return jsonify(error='Not logged in')
    conn = sqlite3.connect('nyewasco.db'); c = conn.cursor()
    e = c.execute("SELECT id FROM employees WHERE staff_number=?", (session['sn'],)).fetchone()
    c.execute("UPDATE attendance SET clock_out_time=? WHERE employee_id=? AND date=? AND clock_in_time IS NOT NULL",
        (datetime.now().strftime('%H:%M:%S'), e[0], date.today().isoformat()))
    log_audit(session['sn'], 'CLOCK_OUT', 'Shift ended')
    conn.commit(); conn.close(); return jsonify(success=True)

if __name__ == '__main__':
    init_db()
    print('\n' + '='*60 + '\nNYEWASCO SYSTEM RUNNING: http://127.0.0.1:5000\nLogin: NYE001 / password\n' + '='*60)
    app.run(debug=True, port=5000)
