import os
import time
import sqlite3
from flask import Flask, request, jsonify, Response, render_template_string, send_from_directory

app = Flask(__name__)

BASE_DIR = r"C:\Users\Tar\Desktop\BridgeDemo"
CAPTURE_DIR = os.path.join(BASE_DIR, "captures")
DB_PATH = os.path.join(BASE_DIR, "bridge_logs.db")
os.makedirs(CAPTURE_DIR, exist_ok=True)

live_state = {
    "risk_level": "NORMAL",
    "detected_parts": "None",
    "hold_duration": 0.0,
    "pole_id": "เสา P8-N04 (ฝั่งพระนคร)",
    "camera_id": "CAM-01",
    "last_update": 0
}
latest_jpeg_frame = None

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS incident_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            camera_id TEXT,
            pole_id TEXT,
            risk_level TEXT,
            event_type TEXT,
            duration REAL,
            snapshot_file TEXT,
            video_file TEXT,
            status TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

HTML_PAGE = """
<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <title>ศูนย์เฝ้าระวังความปลอดภัยและอุบัติเหตุอัจฉริยะ - สะพานพระราม 8</title>
    <style>
        * { box-sizing: border-box; font-family: 'Segoe UI', Tahoma, sans-serif; }
        body { margin: 0; background: #0b0f19; color: #e2e8f0; padding: 16px; }
        .header { display: flex; justify-content: space-between; align-items: center; background: #111827; padding: 14px 20px; border-radius: 10px; border: 1px solid #1f2937; margin-bottom: 16px; }
        .header h1 { margin: 0; font-size: 20px; color: #38bdf8; }
        .badge { padding: 8px 16px; border-radius: 20px; font-weight: bold; font-size: 14px; }
        .badge-normal { background: #065f46; color: #34d399; }
        .badge-warning { background: #92400e; color: #fcd34d; }
        .badge-danger { background: #991b1b; color: #fca5a5; animation: blink 0.7s infinite; }
        .badge-fallen { background: #6b21a8; color: #f3e8ff; border: 1px solid #d8b4fe; animation: blink 0.7s infinite; }
        .badge-vehicle { background: #854d0e; color: #fef08a; border: 1px solid #facc15; animation: blink 0.7s infinite; }

        .main-grid { display: grid; grid-template-columns: 1.6fr 1fr; gap: 16px; margin-bottom: 16px; }
        .panel { background: #111827; border: 1px solid #1f2937; border-radius: 10px; padding: 14px; }
        .panel-title { font-size: 16px; font-weight: bold; margin-bottom: 12px; color: #94a3b8; display: flex; justify-content: space-between; align-items: center; }

        .cctv-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
        .cam-box { position: relative; background: #000; border: 3px solid #334155; border-radius: 8px; overflow: hidden; aspect-ratio: 16/9; display: flex; align-items: center; justify-content: center; }
        .cam-box.warning-border { border-color: #f59e0b; box-shadow: 0 0 15px rgba(245, 158, 11, 0.6); }
        .cam-box.danger-border { border-color: #ef4444; box-shadow: 0 0 22px rgba(239, 68, 68, 0.9); animation: borderPulse 0.6s infinite; }
        .cam-box.fallen-border { border-color: #c084fc; box-shadow: 0 0 22px rgba(192, 132, 252, 0.9); animation: borderPulse 0.6s infinite; }
        .cam-box.vehicle-border { border-color: #facc15; box-shadow: 0 0 22px rgba(250, 204, 21, 0.9); animation: borderPulse 0.6s infinite; }
        .cam-box img { width: 100%; height: 100%; object-fit: cover; }
        .cam-label { position: absolute; top: 8px; left: 8px; background: rgba(0,0,0,0.75); padding: 4px 8px; border-radius: 4px; font-size: 12px; color: #38bdf8; }
        .cam-overlay { position: absolute; bottom: 0; width: 100%; text-align: center; padding: 6px; font-weight: bold; font-size: 13px; display: none; }
        .overlay-warning { background: rgba(217, 119, 6, 0.92); color: #fff; }
        .overlay-danger { background: rgba(220, 38, 38, 0.95); color: #fff; }
        .overlay-fallen { background: rgba(126, 34, 206, 0.95); color: #fff; }
        .overlay-vehicle { background: rgba(202, 138, 4, 0.95); color: #000; }

        .led-sign-wrapper { background: #050505; border: 6px solid #27272a; border-radius: 10px; padding: 18px; text-align: center; box-shadow: inset 0 0 25px #000; margin-bottom: 14px; }
        .led-sign-wrapper.led-warning { border-color: #f59e0b; box-shadow: 0 0 18px rgba(245,158,11,0.5); }
        .led-sign-wrapper.led-danger { border-color: #ef4444; box-shadow: 0 0 25px rgba(239,68,68,0.8); }
        .led-sign-wrapper.led-fallen { border-color: #c084fc; box-shadow: 0 0 25px rgba(192,132,252,0.8); }
        .led-sign-wrapper.led-vehicle { border-color: #facc15; box-shadow: 0 0 25px rgba(250,204,21,0.8); }
        .led-pole-tag { display: inline-block; background: #1e293b; color: #f8fafc; padding: 4px 12px; border-radius: 4px; font-size: 13px; margin-bottom: 10px; }
        .led-screen { font-family: 'Courier New', monospace; font-weight: bold; padding: 16px; border-radius: 6px; background: #090d16; min-height: 135px; display: flex; flex-direction: column; justify-content: center; gap: 8px; }
        .led-normal-text { color: #22c55e; font-size: 18px; text-shadow: 0 0 8px #22c55e; }
        .led-warning-title { color: #fbbf24; font-size: 20px; text-shadow: 0 0 8px #f59e0b; }
        .led-danger-title { color: #ef4444; font-size: 22px; text-shadow: 0 0 12px #ef4444; animation: blink 0.6s infinite; }
        .led-fallen-title { color: #e879f9; font-size: 22px; text-shadow: 0 0 12px #d946ef; animation: blink 0.6s infinite; }
        .led-vehicle-title { color: #facc15; font-size: 22px; text-shadow: 0 0 12px #eab308; animation: blink 0.6s infinite; }
        .led-sub-text { color: #f8fafc; font-size: 15px; line-height: 1.4; }

        .telemetry-box { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; }
        .stat-card { background: #1e293b; padding: 10px; border-radius: 8px; text-align: center; }
        .stat-val { font-size: 18px; font-weight: bold; color: #38bdf8; margin-top: 4px; }

        table { width: 100%; border-collapse: collapse; font-size: 14px; }
        th, td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #1f2937; }
        th { background: #1e293b; color: #94a3b8; }
        .btn { padding: 6px 10px; border: none; border-radius: 5px; cursor: pointer; font-size: 12px; font-weight: bold; text-decoration: none; display: inline-block; margin-right: 4px; }
        .btn-view { background: #0284c7; color: #fff; }
        .btn-resolve { background: #16a34a; color: #fff; }
        .btn-sound { background: #475569; color: #fff; }
        .tag-warn { background: #92400e; color: #fde68a; padding: 3px 8px; border-radius: 4px; font-size: 12px; }
        .tag-dang { background: #991b1b; color: #fecaca; padding: 3px 8px; border-radius: 4px; font-size: 12px; }
        .tag-fall { background: #6b21a8; color: #f3e8ff; padding: 3px 8px; border-radius: 4px; font-size: 12px; }
        .tag-veh { background: #854d0e; color: #fef08a; padding: 3px 8px; border-radius: 4px; font-size: 12px; }

        @keyframes blink { 50% { opacity: 0.3; } }
        @keyframes borderPulse { 50% { border-color: #ffffff; } }
    </style>
</head>
<body>

<div class="header">
    <div>
        <h1>🌉 ศูนย์เฝ้าระวังความปลอดภัยและอุบัติเหตุอัจฉริยะ (สะพานพระราม 8)</h1>
        <small style="color:#94a3b8;">Zone1: แขน & หัวไหล่ทั้ง 2 ข้าง / ช่วงล่าง | Zone2: แยกตรวจจับผู้หมดสติล้มนอน & รถยนต์รุกล้ำทางเดิน</small>
    </div>
    <div style="display:flex; gap:10px; align-items:center;">
        <button id="sound-btn" class="btn btn-sound" onclick="toggleSound()">🔇 เปิดเสียงเตือนห้องควบคุม</button>
        <div id="global-badge" class="badge badge-normal">🟢 สถานะปกติ (NORMAL)</div>
    </div>
</div>

<div class="main-grid">
    <div class="panel">
        <div class="panel-title">
            <span>📹 มุมมองกล้องวงจรปิด (CCTV Matrix)</span>
            <span style="color:#38bdf8;">CAM-01: Pose + Fall + Vehicle Detection</span>
        </div>
        <div class="cctv-grid">
            <div id="cam1-box" class="cam-box">
                <span class="cam-label">🔴 CAM-01 | เสา P8-N04 (Zone1 ราว / Zone2 ทางเดิน)</span>
                <img src="/video_feed" alt="Waiting for CiRA CORE stream..." />
                <div id="cam1-overlay" class="cam-overlay"></div>
            </div>
            <div class="cam-box">
                <span class="cam-label">🟢 CAM-02 | เสา P8-N08 (กลางสะพานฝั่งเหนือ)</span>
                <div style="color:#64748b; font-size:13px;">[กล้องเฝ้าระวังจุดที่ 2 - เหตุการณ์ปกติ]</div>
            </div>
            <div class="cam-box">
                <span class="cam-label">🟢 CAM-03 | เสา P8-S02 (ฝั่งธนบุรี)</span>
                <div style="color:#64748b; font-size:13px;">[กล้องเฝ้าระวังจุดที่ 3 - เหตุการณ์ปกติ]</div>
            </div>
            <div class="cam-box">
                <span class="cam-label">🟢 CAM-04 | ทางเดินใต้สะพาน</span>
                <div style="color:#64748b; font-size:13px;">[กล้องเฝ้าระวังจุดที่ 4 - เหตุการณ์ปกติ]</div>
            </div>
        </div>
    </div>

    <div class="panel">
        <div class="panel-title">
            <span>🪧 จำลองป้ายไฟ LED อัจฉริยะริมทางเดินสะพาน (สำหรับผู้สัญจรผ่านไปมา)</span>
        </div>
        <div id="led-wrapper" class="led-sign-wrapper">
            <div class="led-pole-tag">ตำแหน่งป้าย: เสา P8-N04 (ระยะห่างจุดเกิดเหตุ 5 เมตร)</div>
            <div id="led-screen" class="led-screen">
                <div class="led-normal-text">🟢 สะพานพระราม 8 ยินดีต้อนรับ</div>
                <div style="color:#38bdf8; font-size:14px;">ขอให้ทุกท่านเดินทางโดยสวัสดิภาพ | เจ็บป่วยฉุกเฉิน 1669 | สุขภาพใจ 1323</div>
            </div>
        </div>

        <div class="telemetry-box">
            <div class="stat-card">
                <div style="font-size:12px; color:#94a3b8;">เหตุการณ์/อวัยวะที่ตรวจพบ</div>
                <div id="val-parts" class="stat-val">None</div>
            </div>
            <div class="stat-card">
                <div style="font-size:12px; color:#94a3b8;">ระยะเวลาต่อเนื่อง</div>
                <div id="val-duration" class="stat-val">0.0 s</div>
            </div>
        </div>
    </div>
</div>

<div class="panel">
    <div class="panel-title">
        <span>🗄️ ประวัติการแจ้งเตือนและหลักฐานภาพ/วิดีโอ (SQLite Database Logs)</span>
        <button class="btn btn-resolve" onclick="resetAlertState()">🔄 รีเซ็ตสถานะหน้าจอ</button>
    </div>
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>วัน-เวลา</th>
                <th>ประเภทเหตุการณ์</th>
                <th>พิกัดเสา</th>
                <th>รายละเอียดเหตุการณ์</th>
                <th>หลักฐาน</th>
                <th>สถานะ</th>
                <th>จัดการ</th>
            </tr>
        </thead>
        <tbody id="log-table-body">
            <tr><td colspan="8" style="text-align:center; color:#64748b;">ยังไม่มีประวัติการแจ้งเตือน</td></tr>
        </tbody>
    </table>
</div>

<script>
let soundEnabled = false;
let audioCtx = null;

function toggleSound() {
    soundEnabled = !soundEnabled;
    if (soundEnabled && !audioCtx) {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    const btn = document.getElementById('sound-btn');
    btn.innerText = soundEnabled ? '🔊 เปิดเสียงเตือนแล้ว' : '🔇 เปิดเสียงเตือนห้องควบคุม';
    btn.style.background = soundEnabled ? '#0284c7' : '#475569';
}

function playBeep() {
    if (!soundEnabled || !audioCtx) return;
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = 'sawtooth';
    osc.frequency.setValueAtTime(880, audioCtx.currentTime);
    gain.gain.setValueAtTime(0.08, audioCtx.currentTime);
    osc.connect(gain);
    gain.connect(audioCtx.destination);
    osc.start();
    osc.stop(audioCtx.currentTime + 0.18);
}

async function fetchStatus() {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();
        const st = data.live;

        document.getElementById('val-parts').innerText = st.detected_parts;
        document.getElementById('val-duration').innerText = st.hold_duration.toFixed(1) + ' s';

        const cam1Box = document.getElementById('cam1-box');
        const cam1Overlay = document.getElementById('cam1-overlay');
        const ledWrapper = document.getElementById('led-wrapper');
        const ledScreen = document.getElementById('led-screen');
        const globalBadge = document.getElementById('global-badge');

        cam1Box.classList.remove('warning-border', 'danger-border', 'fallen-border', 'vehicle-border');
        ledWrapper.classList.remove('led-warning', 'led-danger', 'led-fallen', 'led-vehicle');

        if (st.risk_level === 'VEHICLE') {
            cam1Box.classList.add('vehicle-border');
            cam1Overlay.className = 'cam-overlay overlay-vehicle';
            cam1Overlay.style.display = 'block';
            cam1Overlay.innerText = '🚗 แจ้งเตือนรถยนต์! ตรวจพบรถยนต์รุกล้ำเข้ามาบนทางเดิน (Zone2)';

            ledWrapper.classList.add('led-vehicle');
            globalBadge.className = 'badge badge-vehicle';
            globalBadge.innerText = '🚗 รถยนต์รุกล้ำทางเดิน (VEHICLE): ' + st.pole_id;

            ledScreen.innerHTML = `
                <div class="led-vehicle-title">🚗 ระวังอันตราย! มีรถยนต์รุกล้ำทางเดิน</div>
                <div class="led-sub-text">
                    บริเวณ <b style="color:#fef08a;">[${st.pole_id}]</b> โปรดหลบเข้าพื้นที่ปลอดภัย<br>
                    ห้ามกีดขวางเส้นทาง (แจ้งเจ้าหน้าที่ตำรวจจราจรเข้าตรวจสอบแล้ว)
                </div>
            `;
            playBeep();
        } else if (st.risk_level === 'FALLEN') {
            cam1Box.classList.add('fallen-border');
            cam1Overlay.className = 'cam-overlay overlay-fallen';
            cam1Overlay.style.display = 'block';
            cam1Overlay.innerText = '🚑 พบผู้หมดสติ! ตรวจพบคนล้มนอนราบกับพื้นทางเดิน (Zone2)';

            ledWrapper.classList.add('led-fallen');
            globalBadge.className = 'badge badge-fallen';
            globalBadge.innerText = '🚑 พบผู้หมดสติล้มนอน (FALLEN): ' + st.pole_id;

            ledScreen.innerHTML = `
                <div class="led-fallen-title">🚑 ขอความช่วยเหลือด่วน! พบผู้หมดสติล้มนอน</div>
                <div class="led-sub-text">
                    บริเวณ <b style="color:#f0abfc;">[${st.pole_id}]</b> ขอความร่วมมือผู้สัญจรเข้าปฐมพยาบาลเบื้องต้น<br>
                    ระบบได้ประสานหน่วยกู้ชีพ 1669 เดินทางมายังจุดเกิดเหตุแล้ว
                </div>
            `;
            playBeep();
        } else if (st.risk_level === 'DANGER') {
            cam1Box.classList.add('danger-border');
            cam1Overlay.className = 'cam-overlay overlay-danger';
            cam1Overlay.style.display = 'block';
            cam1Overlay.innerText = '🚨 อันตราย! พบส่วนลำตัวช่วงล่าง/สะโพกข้ามแนวราวสะพาน';

            ledWrapper.classList.add('led-danger');
            globalBadge.className = 'badge badge-danger';
            globalBadge.innerText = '🚨 ระดับอันตราย (DANGER): ' + st.pole_id;

            ledScreen.innerHTML = `
                <div class="led-danger-title">🚨 แจ้งเตือนฉุกเฉิน! ขอความช่วยเหลือด่วน</div>
                <div class="led-sub-text">
                    พบผู้มีความเสี่ยงสูงบริเวณ <b style="color:#facc15;">[${st.pole_id}]</b><br>
                    ขอความร่วมมือผู้สัญจรใกล้เคียงเข้าพูดคุยช่วยเหลือ ระหว่างรอเจ้าหน้าที่ตำรวจ
                </div>
            `;
            playBeep();
        } else if (st.risk_level === 'WARNING') {
            cam1Box.classList.add('warning-border');
            cam1Overlay.className = 'cam-overlay overlay-warning';
            cam1Overlay.style.display = 'block';
            cam1Overlay.innerText = '⚠️ เฝ้าระวัง: พบหัวไหล่ทั้ง 2 ข้างหรือแขนยื่นเข้าโซนราวสะพาน';

            ledWrapper.classList.add('led-warning');
            globalBadge.className = 'badge badge-warning';
            globalBadge.innerText = '⚠️ ระดับเฝ้าระวัง (WARNING): ' + st.pole_id;

            ledScreen.innerHTML = `
                <div class="led-warning-title">⚠️ โปรดระมัดระวังความปลอดภัย</div>
                <div class="led-sub-text">
                    บริเวณ <b style="color:#fde68a;">[${st.pole_id}]</b> กรุณาอย่าปีนป่ายหรือชะโงกตัวเกินราวสะพาน<br>
                    ต้องการปรึกษาปัญหาชีวิต โทรสายด่วนสุขภาพใจ 1323 ฟรีตลอด 24 ชม.
                </div>
            `;
        } else {
            cam1Overlay.style.display = 'none';
            globalBadge.className = 'badge badge-normal';
            globalBadge.innerText = '🟢 สถานะปกติ (NORMAL)';

            ledScreen.innerHTML = `
                <div class="led-normal-text">🟢 สะพานพระราม 8 ยินดีต้อนรับ</div>
                <div style="color:#38bdf8; font-size:14px;">ขอให้ทุกท่านเดินทางโดยสวัสดิภาพ | เจ็บป่วยฉุกเฉิน 1669 | สุขภาพใจ 1323</div>
            `;
        }

        const tbody = document.getElementById('log-table-body');
        if (data.logs.length > 0) {
            tbody.innerHTML = data.logs.map(row => {
                let tagClass = 'tag-warn';
                let tagLabel = row.risk_level;
                if (row.risk_level === 'DANGER') { tagClass = 'tag-dang'; tagLabel = '🚨 DANGER'; }
                if (row.risk_level === 'FALLEN') { tagClass = 'tag-fall'; tagLabel = '🚑 ผู้หมดสติ'; }
                if (row.risk_level === 'VEHICLE') { tagClass = 'tag-veh'; tagLabel = '🚗 รถยนต์รุกล้ำ'; }
                if (row.risk_level === 'WARNING') { tagClass = 'tag-warn'; tagLabel = '⚠️ WARNING'; }

                return `
                <tr>
                    <td>#${row.id}</td>
                    <td>${row.timestamp}</td>
                    <td><span class="${tagClass}">${tagLabel}</span></td>
                    <td><b>${row.pole_id}</b></td>
                    <td>${row.event_type}</td>
                    <td>
                        <a class="btn btn-view" href="/captures/${row.snapshot_file}" target="_blank">🖼️ ภาพ</a>
                        ${row.video_file ? `<a class="btn btn-view" href="/captures/${row.video_file}" target="_blank">🎬 คลิป</a>` : ''}
                    </td>
                    <td style="color:${row.status === 'เข้าช่วยเหลือแล้ว' ? '#4ade80' : '#f87171'}; font-weight:bold;">${row.status}</td>
                    <td>
                        ${row.status !== 'เข้าช่วยเหลือแล้ว' ? `<button class="btn btn-resolve" onclick="resolveIncident(${row.id})">✅ ปิดเคส</button>` : '-'}
                    </td>
                </tr>
            `}).join('');
        }
    } catch (e) {}
}

async function resolveIncident(id) {
    await fetch('/api/resolve/' + id, { method: 'POST' });
    fetchStatus();
}

async function resetAlertState() {
    await fetch('/api/reset_alert', { method: 'POST' });
    fetchStatus();
}

setInterval(fetchStatus, 500);
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_PAGE)

@app.route("/api/live", methods=["POST"])
def update_live():
    global latest_jpeg_frame, live_state
    live_state["risk_level"] = request.form.get("risk_level", "NORMAL")
    live_state["detected_parts"] = request.form.get("detected_parts", "None")
    live_state["hold_duration"] = float(request.form.get("hold_duration", 0.0))
    live_state["pole_id"] = request.form.get("pole_id", "เสา P8-N04 (ฝั่งพระนคร)")
    live_state["last_update"] = time.time()

    if "frame" in request.files:
        latest_jpeg_frame = request.files["frame"].read()
    return jsonify({"ok": True})

@app.route("/video_feed")
def video_feed():
    def generate():
        while True:
            if latest_jpeg_frame is not None:
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n" + latest_jpeg_frame + b"\r\n")
            time.sleep(0.06)
    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/api/incident", methods=["POST"])
def record_incident():
    data = request.json
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO incident_logs (timestamp, camera_id, pole_id, risk_level, event_type, duration, snapshot_file, video_file, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("timestamp"),
        data.get("camera_id", "CAM-01"),
        data.get("pole_id", "เสา P8-N04 (ฝั่งพระนคร)"),
        data.get("risk_level", "WARNING"),
        data.get("event_type", ""),
        float(data.get("duration", 0.0)),
        data.get("snapshot_file", ""),
        data.get("video_file", ""),
        "รอตรวจสอบ"
    ))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/api/status")
def get_status():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM incident_logs ORDER BY id DESC LIMIT 15")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify({"live": live_state, "logs": rows})

@app.route("/api/resolve/<int:inc_id>", methods=["POST"])
def resolve_incident(inc_id):
    global live_state
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE incident_logs SET status = 'เข้าช่วยเหลือแล้ว' WHERE id = ?", (inc_id,))
    conn.commit()
    conn.close()
    live_state["risk_level"] = "NORMAL"
    return jsonify({"ok": True})

@app.route("/api/reset_alert", methods=["POST"])
def reset_alert():
    global live_state
    live_state["risk_level"] = "NORMAL"
    live_state["hold_duration"] = 0.0
    return jsonify({"ok": True})

@app.route("/captures/<path:filename>")
def serve_capture(filename):
    return send_from_directory(CAPTURE_DIR, filename)

if __name__ == "__main__":
    print("=== Bridge Smart Monitoring Server Running at http://127.0.0.1:8000 ===")
    app.run(host="0.0.0.0", port=8000, threaded=True)