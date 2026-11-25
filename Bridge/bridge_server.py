import os
import json
import time
import sqlite3
from flask import Flask, request, jsonify, Response, render_template_string, send_from_directory

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CAPTURE_DIR = os.path.join(BASE_DIR, "captures")
DB_PATH = os.path.join(BASE_DIR, "bridge_logs.db")
ZONE_CONFIG_PATH = os.path.join(BASE_DIR, "zone_config.json")
os.makedirs(CAPTURE_DIR, exist_ok=True)

DEFAULT_ZONE_POINTS = [[930, 150], [1050, 150], [1200, 680], [1020, 680]]


def load_zone_points():
    if os.path.exists(ZONE_CONFIG_PATH):
        try:
            with open(ZONE_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                pts = data.get("points", [])
                if isinstance(pts, list) and len(pts) >= 3:
                    return pts
        except Exception:
            pass
    return DEFAULT_ZONE_POINTS


def save_zone_points(points):
    with open(ZONE_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"points": points}, f, indent=2)


if not os.path.exists(ZONE_CONFIG_PATH):
    save_zone_points(DEFAULT_ZONE_POINTS)

# สถานะกล้องที่ 1 (ระบบหลัก: YOLO Pose + Fall + Vehicle)
live_state = {
    "risk_level": "NORMAL",
    "detected_parts": "None",
    "hold_duration": 0.0,
    "pole_id": "เสา P8-N04 (ฝั่งพระนคร)",
    "camera_id": "CAM-01",
    "last_update": 0
}
latest_jpeg_frame = None

# สถานะกล้องที่ 2 (ระบบเปรียบเทียบ: DeepDetect 30% WARNING / >50% DANGER)
live_state_cam2 = {
    "risk_level": "NORMAL",
    "is_alert": False,
    "person_count": 0,
    "max_pct": 0.0,
    "duration": 0.0,
    "pole_id": "เสา P8-N04",
    "camera_id": "CAM-02",
    "last_update": 0
}
latest_jpeg_frame_cam2 = None


def to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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
    <title>RAMA-8 BRIDGE MONITORING SYSTEM</title>
    <style>
        @font-face { font-display: swap; }

        *, *::before, *::after {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        :root {
            --bg-base:    #0a0c10;
            --bg-panel:   #0f1116;
            --bg-inset:   #0b0d12;
            --bg-row-alt: #0d0f14;
            --border:     #1e222b;
            --border-hi:  #272c35;
            --text-1:     #c8ccd4;
            --text-2:     #787e8a;
            --text-3:     #515763;
            --text-head:  #9ba0aa;
            --accent-grn: #27ae60;
            --accent-red: #c0392b;
            --accent-amb: #b7950b;
            --accent-vio: #7c3aed;
            --accent-grn-bg: rgba(39,174,96,0.08);
            --accent-red-bg: rgba(192,57,43,0.10);
            --accent-amb-bg: rgba(183,149,11,0.09);
            --accent-vio-bg: rgba(124,58,237,0.09);
            --radius: 3px;
            --font-data: 'SF Mono', 'Cascadia Mono', 'Consolas', 'Liberation Mono', monospace;
            --font-ui:   'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
        }

        html { font-size: 13px; }
        body {
            background: var(--bg-base);
            color: var(--text-1);
            font-family: var(--font-ui);
            line-height: 1.4;
            padding: 0;
            -webkit-font-smoothing: antialiased;
            overflow-x: hidden;
        }

        .tn { font-variant-numeric: tabular-nums; }
        .mono { font-family: var(--font-data); }
        .icon-svg {
            width: 14px; height: 14px;
            stroke: currentColor; stroke-width: 1.6;
            fill: none; stroke-linecap: round; stroke-linejoin: round;
            flex-shrink: 0;
            vertical-align: -2px;
        }
        .dot {
            width: 6px; height: 6px;
            border-radius: 50%;
            display: inline-block;
            flex-shrink: 0;
        }
        .dot-ok      { background: var(--accent-grn); }
        .dot-warn    { background: var(--accent-amb); }
        .dot-danger  { background: var(--accent-red); }
        .dot-fallen  { background: var(--accent-vio); }
        .dot-vehicle { background: var(--accent-amb); }
        .dot-idle    { background: var(--text-3); }
        .dot-live    { background: var(--accent-red); }

        /* ---- Top Bar ---- */
        .topbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: var(--bg-panel);
            border-bottom: 1px solid var(--border);
            padding: 0 20px;
            height: 44px;
            gap: 12px;
            user-select: none;
        }
        .topbar-left {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .topbar-sys {
            font-family: var(--font-data);
            font-size: 12px;
            font-weight: 600;
            color: var(--text-2);
            letter-spacing: 0.8px;
            text-transform: uppercase;
        }
        .topbar-sep {
            width: 1px;
            height: 18px;
            background: var(--border-hi);
        }
        .topbar-zone {
            font-size: 11px;
            color: var(--text-3);
            font-family: var(--font-data);
            letter-spacing: 0.3px;
        }
        .topbar-right {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .topbar-clock {
            font-family: var(--font-data);
            font-size: 12px;
            color: var(--text-2);
            font-variant-numeric: tabular-nums;
            letter-spacing: 0.5px;
        }

        .status-ind {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 4px 10px;
            border-radius: var(--radius);
            font-family: var(--font-data);
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0.6px;
            text-transform: uppercase;
            border: 1px solid transparent;
            white-space: nowrap;
        }
        .si-normal  { background: var(--accent-grn-bg); color: var(--accent-grn); border-color: rgba(39,174,96,0.22); }
        .si-warning { background: var(--accent-amb-bg); color: var(--accent-amb); border-color: rgba(183,149,11,0.28); }
        .si-danger  { background: var(--accent-red-bg); color: var(--accent-red); border-color: rgba(192,57,43,0.30); }
        .si-fallen  { background: var(--accent-vio-bg); color: var(--accent-vio); border-color: rgba(124,58,237,0.30); }
        .si-vehicle { background: var(--accent-amb-bg); color: var(--accent-amb); border-color: rgba(183,149,11,0.30); }

        @keyframes pulse-opacity { 0%,100%{opacity:1} 50%{opacity:0.4} }
        @keyframes border-flash { 0%,100%{border-color:var(--accent-red)} 50%{border-color:var(--border)} }

        .btn {
            display: inline-flex;
            align-items: center;
            gap: 5px;
            padding: 4px 9px;
            border: 1px solid var(--border-hi);
            border-radius: var(--radius);
            background: var(--bg-panel);
            color: var(--text-2);
            font-family: var(--font-data);
            font-size: 11px;
            font-weight: 500;
            cursor: pointer;
            text-decoration: none;
            letter-spacing: 0.3px;
            transition: background 0.15s;
        }
        .btn:hover { background: #181c24; color: var(--text-1); }
        .btn-resolve {
            border-color: rgba(39,174,96,0.28);
            color: var(--accent-grn);
        }
        .btn-resolve:hover { background: rgba(39,174,96,0.10); }
        .btn-zone {
            border-color: rgba(250,204,21,0.35);
            color: #facc15;
        }
        .btn-zone.drawing {
            background: rgba(250,204,21,0.15);
            border-color: #facc15;
            color: #fef08a;
        }
        .btn-sound.active {
            border-color: rgba(96,165,250,0.35);
            color: #60a5fa;
            background: rgba(96,165,250,0.08);
        }

        .shell {
            display: block;
            min-height: calc(100vh - 44px);
        }
        .workspace {
            display: grid;
            grid-template-columns: 1.55fr 1fr;
            grid-template-rows: auto 1fr;
            gap: 1px;
            background: var(--border);
            min-height: calc(100vh - 44px);
        }

        .pnl {
            background: var(--bg-panel);
            padding: 14px 16px;
            overflow-y: auto;
        }
        .pnl-label {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
            margin-bottom: 10px;
        }
        .pnl-label-left {
            display: inline-flex;
            align-items: center;
            gap: 7px;
            font-family: var(--font-data);
            font-size: 11px;
            font-weight: 600;
            color: var(--text-2);
            letter-spacing: 0.6px;
            text-transform: uppercase;
        }
        .pnl-label-right {
            font-family: var(--font-data);
            font-size: 10px;
            color: var(--text-3);
            letter-spacing: 0.4px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        /* ---- CCTV Grid ---- */
        .cctv-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 6px;
        }
        .cam {
            position: relative;
            background: #060810;
            border: 1px solid var(--border);
            border-radius: var(--radius);
            overflow: hidden;
            aspect-ratio: 16/9;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .cam.draw-cursor {
            cursor: crosshair;
            border-color: #facc15 !important;
            box-shadow: 0 0 12px rgba(250,204,21,0.35);
        }
        .cam img {
            width: 100%; height: 100%;
            object-fit: fill;
            display: block;
            position: relative;
            z-index: 2;
            user-select: none;
            -webkit-user-drag: none;
        }
        .cam-svg-overlay {
            position: absolute;
            top: 0; left: 0;
            width: 100%; height: 100%;
            z-index: 5;
            pointer-events: none;
        }
        .cam-tag {
            position: absolute;
            top: 6px; left: 6px;
            z-index: 3;
            display: inline-flex;
            align-items: center;
            gap: 5px;
            background: rgba(10,12,16,0.92);
            border: 1px solid var(--border);
            padding: 3px 7px;
            border-radius: 2px;
            font-family: var(--font-data);
            font-size: 10px;
            color: var(--text-2);
            letter-spacing: 0.4px;
            pointer-events: none;
        }
        .cam-ts {
            position: absolute;
            bottom: 6px; right: 6px;
            z-index: 3;
            font-family: var(--font-data);
            font-size: 9px;
            color: var(--text-3);
            background: rgba(10,12,16,0.85);
            padding: 2px 5px;
            border-radius: 2px;
            font-variant-numeric: tabular-nums;
            pointer-events: none;
        }
        .cam-idle-msg {
            position: absolute;
            z-index: 1;
            display: inline-flex;
            align-items: center;
            gap: 5px;
            font-family: var(--font-data);
            font-size: 10px;
            color: var(--text-3);
            letter-spacing: 0.5px;
        }
        .cam-alert-bar {
            position: absolute;
            bottom: 0; left: 0; right: 0;
            z-index: 4;
            padding: 5px 8px;
            font-family: var(--font-data);
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 0.3px;
            text-align: center;
            display: none;
            pointer-events: none;
        }
        .bar-warning { background: rgba(183,149,11,0.92); color: #fefce8; }
        .bar-danger  { background: rgba(192,57,43,0.94); color: #fef2f2; }
        .bar-fallen  { background: rgba(124,58,237,0.92); color: #f5f3ff; }
        .bar-vehicle { background: rgba(183,149,11,0.92); color: #fefce8; }
        .bar-drawing { background: rgba(202,138,4,0.95); color: #000; }

        .cam.border-warn    { border-color: var(--accent-amb); }
        .cam.border-danger  { border-color: var(--accent-red); }
        .cam.border-fallen  { border-color: var(--accent-vio); }
        .cam.border-vehicle { border-color: var(--accent-amb); }

        /* ---- Right Panel: LED + Telemetry ---- */
        .right-stack { display: flex; flex-direction: column; gap: 1px; background: var(--border); }
        .right-stack .pnl { flex: 1; }

        .led-frame {
            background: #060810;
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 12px 14px;
            margin-bottom: 10px;
        }
        .led-frame.lf-warn    { border-color: var(--accent-amb); }
        .led-frame.lf-danger  { border-color: var(--accent-red); }
        .led-frame.lf-fallen  { border-color: var(--accent-vio); }
        .led-frame.lf-vehicle { border-color: var(--accent-amb); }
        .led-loc {
            font-family: var(--font-data);
            font-size: 10px;
            color: var(--text-3);
            margin-bottom: 8px;
            letter-spacing: 0.4px;
            display: flex;
            justify-content: space-between;
        }
        .led-dual-container {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        .led-ch-box {
            background: var(--bg-inset);
            border: 1px solid var(--border);
            border-radius: 2px;
            padding: 8px 10px;
            font-family: var(--font-data);
        }
        .led-ch-header {
            font-size: 9px;
            color: var(--text-3);
            letter-spacing: 0.5px;
            margin-bottom: 4px;
            display: flex;
            align-items: center;
            gap: 5px;
        }
        .led-title-normal  { color: var(--accent-grn); font-size: 13px; font-weight: 700; }
        .led-title-warn    { color: var(--accent-amb); font-size: 14px; font-weight: 700; }
        .led-title-danger  { color: var(--accent-red); font-size: 14px; font-weight: 700; animation: pulse-opacity 0.8s infinite; }
        .led-title-fallen  { color: var(--accent-vio); font-size: 14px; font-weight: 700; animation: pulse-opacity 0.8s infinite; }
        .led-title-vehicle { color: var(--accent-amb); font-size: 14px; font-weight: 700; animation: pulse-opacity 0.8s infinite; }
        .led-desc {
            color: var(--text-2);
            font-size: 11px;
            font-weight: 400;
            line-height: 1.45;
            margin-top: 3px;
        }

        .telem-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 6px;
        }
        .telem-card {
            background: var(--bg-inset);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 8px 10px;
            text-align: center;
        }
        .telem-lbl {
            font-size: 9px;
            color: var(--text-3);
            font-family: var(--font-data);
            letter-spacing: 0.4px;
            text-transform: uppercase;
            margin-bottom: 3px;
        }
        .telem-val {
            font-size: 15px;
            font-weight: 600;
            color: var(--text-1);
            font-family: var(--font-data);
            font-variant-numeric: tabular-nums;
        }

        .log-pnl {
            grid-column: 1 / -1;
        }
        .filter-bar {
            display: inline-flex;
            align-items: center;
            gap: 2px;
            background: var(--bg-inset);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 2px;
        }
        .filter-btn {
            font-family: var(--font-data);
            font-size: 10px;
            padding: 4px 10px;
            border: none;
            border-radius: 2px;
            background: transparent;
            color: var(--text-3);
            cursor: pointer;
            letter-spacing: 0.3px;
            transition: background 0.12s, color 0.12s;
        }
        .filter-btn:hover { color: var(--text-2); }
        .filter-btn.active {
            background: var(--bg-panel);
            color: var(--text-1);
            box-shadow: 0 1px 2px rgba(0,0,0,0.3);
        }

        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
            margin-top: 8px;
        }
        th {
            padding: 7px 10px;
            text-align: left;
            font-family: var(--font-data);
            font-size: 10px;
            font-weight: 600;
            color: var(--text-3);
            letter-spacing: 0.5px;
            text-transform: uppercase;
            background: var(--bg-inset);
            border-bottom: 1px solid var(--border);
            white-space: nowrap;
        }
        td {
            padding: 7px 10px;
            border-bottom: 1px solid #14171d;
            font-variant-numeric: tabular-nums;
            color: var(--text-2);
            white-space: nowrap;
        }
        tr:hover td { background: rgba(255,255,255,0.015); }
        td .mono { font-family: var(--font-data); }

        .tag {
            display: inline-flex;
            align-items: center;
            gap: 5px;
            padding: 2px 7px;
            border-radius: 2px;
            font-family: var(--font-data);
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 0.3px;
        }
        .tag-warn { background: var(--accent-amb-bg); color: var(--accent-amb); }
        .tag-dang { background: var(--accent-red-bg); color: var(--accent-red); }
        .tag-fall { background: var(--accent-vio-bg); color: var(--accent-vio); }
        .tag-veh  { background: var(--accent-amb-bg); color: var(--accent-amb); }

        .cam-badge-inline {
            display: inline-block;
            padding: 1px 5px;
            margin-right: 5px;
            border-radius: 2px;
            font-size: 10px;
            font-weight: 600;
            background: var(--bg-inset);
            border: 1px solid var(--border-hi);
            color: var(--text-1);
        }

        ::-webkit-scrollbar { width: 5px; }
        ::-webkit-scrollbar-track { background: var(--bg-base); }
        ::-webkit-scrollbar-thumb { background: var(--border-hi); border-radius: 3px; }

        @media (max-width: 960px) {
            .workspace { grid-template-columns: 1fr; grid-template-rows: auto auto auto; }
            .cctv-grid { height: auto; }
        }
    </style>
</head>
<body>

<!-- ==================== TOP BAR ==================== -->
<div class="topbar">
    <div class="topbar-left">
        <svg class="icon-svg" viewBox="0 0 24 24" style="width:16px;height:16px;color:var(--text-3);">
            <path d="M3 18h18M5 18v-6a7 7 0 0 1 14 0v6M8 18v-3m4 3v-4m4 4v-3"/>
        </svg>
        <span class="topbar-sys">RAMA-8 BRIDGE MONITORING</span>
        <span class="topbar-sep"></span>
        <span class="topbar-zone">CAM-01: POSE &amp; ACCIDENT &mdash; CAM-02: DEEPDETECT (30% WARN / &gt;50% DANGER)</span>
    </div>
    <div class="topbar-right">
        <span id="topbar-clock" class="topbar-clock"></span>
        <span class="topbar-sep"></span>
        <button id="sound-btn" class="btn btn-sound" onclick="toggleSound()">
            <svg id="sound-icon" class="icon-svg" viewBox="0 0 24 24">
                <path d="M11 5L6 9H2v6h4l5 4V5z"/>
                <line x1="23" y1="9" x2="17" y2="15"/>
                <line x1="17" y1="9" x2="23" y2="15"/>
            </svg>
            <span id="sound-label">AUDIO OFF</span>
        </button>
        <div id="global-badge" class="status-ind si-normal">
            <span class="dot dot-ok"></span>
            <span>NORMAL</span>
        </div>
    </div>
</div>

<!-- ==================== WORKSPACE ==================== -->
<div class="shell">
<div class="workspace">

    <!-- ===== LEFT: CCTV Matrix ===== -->
    <div class="pnl">
        <div class="pnl-label">
            <span class="pnl-label-left">
                <svg class="icon-svg" viewBox="0 0 24 24">
                    <path d="M23 7l-7 5 7 5V7z"/>
                    <rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>
                </svg>
                CCTV MATRIX
            </span>
            <span class="pnl-label-right">
                <button id="edit-zone-btn" class="btn btn-zone" onclick="toggleZoneDraw()">
                    <svg class="icon-svg" viewBox="0 0 24 24">
                        <polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5 12 2"/>
                    </svg>
                    <span id="edit-zone-label">EDIT CAM-02 ZONE (คลิกวาดโซน)</span>
                </button>
            </span>
        </div>
        <div class="cctv-grid">
            <!-- CAM-01 -->
            <div id="cam1-box" class="cam">
                <span class="cam-tag">
                    <span class="dot dot-live"></span>
                    CAM-01 [POSE] P8-N04
                </span>
                <span class="cam-idle-msg">WAITING FOR CAM-01 STREAM...</span>
                <img src="/video_feed" alt="cam1 stream" onerror="this.style.display='none'" onload="this.style.display='block'" />
                <span class="cam-ts" id="cam1-ts"></span>
                <div id="cam1-overlay" class="cam-alert-bar"></div>
            </div>

            <!-- CAM-02 -->
            <div id="cam2-box" class="cam" onclick="handleCam2Click(event)">
                <span class="cam-tag">
                    <span id="cam2-dot" class="dot dot-live"></span>
                    CAM-02 [DEEPDETECT] P8-N04
                </span>
                <span class="cam-idle-msg">WAITING FOR CAM-02 STREAM...</span>
                <img id="cam2-img" src="/video_feed_cam2" alt="cam2 stream" onerror="this.style.display='none'" onload="this.style.display='block'" />
                <svg id="zone-draw-svg" class="cam-svg-overlay"></svg>
                <span class="cam-ts" id="cam2-ts"></span>
                <div id="cam2-overlay" class="cam-alert-bar"></div>
            </div>
        </div>
    </div>

    <!-- ===== RIGHT: Dual LED Sign + Telemetry ===== -->
    <div class="right-stack">
        <div class="pnl">
            <div class="pnl-label">
                <span class="pnl-label-left">
                    <svg class="icon-svg" viewBox="0 0 24 24">
                        <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
                        <line x1="8" y1="21" x2="16" y2="21"/>
                        <line x1="12" y1="17" x2="12" y2="21"/>
                    </svg>
                    LED SIGN OUTPUT (DUAL CAMERA)
                </span>
                <span class="pnl-label-right">BILINGUAL DISPLAY</span>
            </div>
            <div id="led-wrapper" class="led-frame">
                <div class="led-loc">
                    <span>POS: P8-N04 (ระยะห่างจุดเกิดเหตุ 5 ม.)</span>
                    <span>CH-01 + CH-02</span>
                </div>
                <div class="led-dual-container">
                    <div class="led-ch-box">
                        <div class="led-ch-header">
                            <span id="led-dot-1" class="dot dot-ok"></span>
                            <span>CAM-01 &bull; YOLO POSE &amp; ACCIDENT MONITOR</span>
                        </div>
                        <div id="led-screen-1">
                            <div class="led-title-normal">RAMA 8 BRIDGE &mdash; ALL CLEAR / สถานะปกติ</div>
                            <div class="led-desc">Emergency / ฉุกเฉิน 1669 | Mental health / สุขภาพใจ 1323</div>
                        </div>
                    </div>

                    <div class="led-ch-box">
                        <div class="led-ch-header">
                            <span id="led-dot-2" class="dot dot-ok"></span>
                            <span>CAM-02 &bull; DEEPDETECT ZONE1 MONITOR</span>
                        </div>
                        <div id="led-screen-2">
                            <div class="led-title-normal">ZONE 1 CLEAR / ไม่พบบุคคลในโซนเฝ้าระวัง</div>
                            <div class="led-desc">Safe passage / ขอให้ทุกท่านเดินทางโดยสวัสดิภาพ</div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="pnl-label" style="margin-top:4px;">
                <span class="pnl-label-left">
                    <svg class="icon-svg" viewBox="0 0 24 24">
                        <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
                    </svg>
                    TELEMETRY
                </span>
            </div>
            <div class="telem-row">
                <div class="telem-card">
                    <div class="telem-lbl">CAM-01 DETECTED</div>
                    <div id="val-parts" class="telem-val" style="font-size:13px;">None</div>
                </div>
                <div class="telem-card">
                    <div class="telem-lbl">CAM-01 HOLD TIME</div>
                    <div id="val-duration" class="telem-val">0.0 s</div>
                </div>
                <div class="telem-card">
                    <div class="telem-lbl">CAM-02 AREA OVERLAP</div>
                    <div id="val-cam2-count" class="telem-val">0.0 %</div>
                </div>
                <div class="telem-card">
                    <div class="telem-lbl">CAM-02 HOLD TIME</div>
                    <div id="val-cam2-duration" class="telem-val">0.0 s</div>
                </div>
            </div>
        </div>
    </div>

    <!-- ===== BOTTOM: Incident Log ===== -->
    <div class="pnl log-pnl">
        <div class="pnl-label">
            <span class="pnl-label-left">
                <svg class="icon-svg" viewBox="0 0 24 24">
                    <ellipse cx="12" cy="5" rx="9" ry="3"/>
                    <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>
                    <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
                </svg>
                INCIDENT LOG
                <span style="color:var(--text-3);font-weight:400;text-transform:none;">&mdash; SQLite</span>
            </span>
            <div style="display:flex;gap:6px;align-items:center;">
                <div class="filter-bar">
                    <button class="filter-btn active" onclick="setFilter('all',this)">ALL</button>
                    <button class="filter-btn" onclick="setFilter('pending',this)">PENDING</button>
                    <button class="filter-btn" onclick="setFilter('resolved',this)">RESOLVED</button>
                </div>
                <button class="btn btn-resolve" onclick="resetAlertState()">
                    <svg class="icon-svg" viewBox="0 0 24 24">
                        <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
                        <path d="M3 3v5h5"/>
                    </svg>
                    RESET
                </button>
            </div>
        </div>
        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>TIMESTAMP</th>
                    <th>TYPE</th>
                    <th>CAMERA / POLE</th>
                    <th>EVENT</th>
                    <th>EVIDENCE</th>
                    <th>STATUS</th>
                    <th>ACTION</th>
                </tr>
            </thead>
            <tbody id="log-table-body">
                <tr><td colspan="8" style="text-align:center;color:var(--text-3);padding:20px;">NO RECORDS</td></tr>
            </tbody>
        </table>
    </div>

</div>
</div>

<script>
let soundEnabled = false;
let audioCtx = null;
let currentFilter = 'all';

let isDrawingZone = false;
let draftScreenPoints = [];
let draftRealPoints = [];

function toggleZoneDraw() {
    isDrawingZone = !isDrawingZone;
    draftScreenPoints = [];
    draftRealPoints = [];
    const btn = document.getElementById('edit-zone-btn');
    const lbl = document.getElementById('edit-zone-label');
    const cam2Box = document.getElementById('cam2-box');
    const cam2Overlay = document.getElementById('cam2-overlay');
    const svg = document.getElementById('zone-draw-svg');
    svg.innerHTML = '';

    if (isDrawingZone) {
        btn.classList.add('drawing');
        lbl.textContent = 'CANCEL DRAW (คลิกครบ 4 จุดบนภาพ)';
        cam2Box.classList.add('draw-cursor');
        cam2Overlay.className = 'cam-alert-bar bar-drawing';
        cam2Overlay.style.display = 'block';
        cam2Overlay.textContent = 'คลิกเมาส์ 4 มุมบนภาพ CAM-02 เพื่อกำหนดกรอบโซน (0/4 จุด)';
    } else {
        btn.classList.remove('drawing');
        lbl.textContent = 'EDIT CAM-02 ZONE (คลิกวาดโซน)';
        cam2Box.classList.remove('draw-cursor');
        cam2Overlay.style.display = 'none';
    }
}

async function handleCam2Click(event) {
    if (!isDrawingZone) return;
    const cam2Box = document.getElementById('cam2-box');
    const img = document.getElementById('cam2-img');
    const rect = cam2Box.getBoundingClientRect();

    const sx = event.clientX - rect.left;
    const sy = event.clientY - rect.top;

    const natW = (img && img.naturalWidth > 0) ? img.naturalWidth : 1280;
    const natH = (img && img.naturalHeight > 0) ? img.naturalHeight : 720;
    const realX = Math.round((sx / rect.width) * natW);
    const realY = Math.round((sy / rect.height) * natH);

    draftScreenPoints.push([sx, sy]);
    draftRealPoints.push([realX, realY]);

    const svg = document.getElementById('zone-draw-svg');
    let html = '';
    if (draftScreenPoints.length >= 2) {
        const ptsStr = draftScreenPoints.map(p => p[0] + ',' + p[1]).join(' ');
        html += '<polygon points="' + ptsStr + '" fill="rgba(250,204,21,0.22)" stroke="#facc15" stroke-width="2" />';
    }
    draftScreenPoints.forEach((p, idx) => {
        html += '<circle cx="' + p[0] + '" cy="' + p[1] + '" r="5" fill="#ef4444" stroke="#fff" stroke-width="1.5" />';
        html += '<text x="' + (p[0] + 8) + '" y="' + (p[1] - 6) + '" fill="#fef08a" font-size="11" font-family="monospace">P' + (idx + 1) + '</text>';
    });
    svg.innerHTML = html;

    const cam2Overlay = document.getElementById('cam2-overlay');
    cam2Overlay.textContent = 'คลิกเมาส์ 4 มุมบนภาพ CAM-02 เพื่อกำหนดกรอบโซน (' + draftRealPoints.length + '/4 จุด)';

    if (draftRealPoints.length === 4) {
        await fetch('/api/set_zone_cam2', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ points: draftRealPoints })
        });
        setTimeout(() => {
            toggleZoneDraw();
        }, 350);
    }
}

function tickClock() {
    const now = new Date();
    const hh = String(now.getHours()).padStart(2,'0');
    const mm = String(now.getMinutes()).padStart(2,'0');
    const ss = String(now.getSeconds()).padStart(2,'0');
    const timeStr = hh + ':' + mm + ':' + ss;
    document.getElementById('topbar-clock').textContent = timeStr;
    const ts1 = document.getElementById('cam1-ts');
    const ts2 = document.getElementById('cam2-ts');
    if (ts1) ts1.textContent = timeStr;
    if (ts2) ts2.textContent = timeStr;
}
tickClock();
setInterval(tickClock, 1000);

function setBadgeContent(el, dotClass, text) {
    el.innerHTML = '<span class="dot ' + dotClass + '"></span><span>' + text + '</span>';
}

function toggleSound() {
    soundEnabled = !soundEnabled;
    if (soundEnabled && !audioCtx) {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    const btn = document.getElementById('sound-btn');
    const label = document.getElementById('sound-label');
    const icon = document.getElementById('sound-icon');
    if (soundEnabled) {
        btn.classList.add('active');
        label.textContent = 'AUDIO ON';
        icon.innerHTML = '<path d="M11 5L6 9H2v6h4l5 4V5z"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>';
    } else {
        btn.classList.remove('active');
        label.textContent = 'AUDIO OFF';
        icon.innerHTML = '<path d="M11 5L6 9H2v6h4l5 4V5z"/><line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/>';
    }
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

function setFilter(mode, el) {
    currentFilter = mode;
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    el.classList.add('active');
    applyFilter();
}

function applyFilter() {
    const rows = document.querySelectorAll('#log-table-body tr[data-status]');
    rows.forEach(r => {
        if (currentFilter === 'all') { r.style.display = ''; return; }
        const st = r.getAttribute('data-status');
        if (currentFilter === 'pending' && st === 'pending') r.style.display = '';
        else if (currentFilter === 'resolved' && st === 'resolved') r.style.display = '';
        else r.style.display = 'none';
    });
}

async function fetchStatus() {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();
        const st = data.live;
        const st2 = data.live_cam2;

        document.getElementById('val-parts').textContent = st.detected_parts;
        document.getElementById('val-duration').textContent = Number(st.hold_duration || 0).toFixed(1) + ' s';
        document.getElementById('val-cam2-count').textContent = Number(st2.max_pct || 0).toFixed(1) + ' % (' + st2.person_count + ')';
        document.getElementById('val-cam2-duration').textContent = Number(st2.duration || 0).toFixed(1) + ' s';

        const cam1Box = document.getElementById('cam1-box');
        const cam1Overlay = document.getElementById('cam1-overlay');
        const cam2Box = document.getElementById('cam2-box');
        const cam2Overlay = document.getElementById('cam2-overlay');

        const ledWrapper = document.getElementById('led-wrapper');
        const ledScreen1 = document.getElementById('led-screen-1');
        const ledScreen2 = document.getElementById('led-screen-2');
        const ledDot1 = document.getElementById('led-dot-1');
        const ledDot2 = document.getElementById('led-dot-2');
        const globalBadge = document.getElementById('global-badge');

        cam1Box.classList.remove('border-warn', 'border-danger', 'border-fallen', 'border-vehicle');
        cam2Box.classList.remove('border-warn', 'border-danger');
        ledWrapper.classList.remove('lf-warn', 'lf-danger', 'lf-fallen', 'lf-vehicle');

        let shouldBeep = false;

        // ==================== 1. อัปเดต CAM-01 & LED ช่องที่ 1 ====================
        if (st.risk_level === 'VEHICLE') {
            cam1Box.classList.add('border-vehicle');
            cam1Overlay.className = 'cam-alert-bar bar-vehicle';
            cam1Overlay.style.display = 'block';
            cam1Overlay.textContent = 'VEHICLE INTRUSION / แจ้งเตือนรถยนต์รุกล้ำทางเดิน (Zone2)';

            ledDot1.className = 'dot dot-vehicle';
            ledScreen1.innerHTML =
                '<div class="led-title-vehicle">VEHICLE INTRUSION / ระวังรถยนต์รุกล้ำทางเดิน</div>' +
                '<div class="led-desc">Area: <b style="color:var(--accent-amb);">[' + st.pole_id + ']</b> &mdash; โปรดหลบเข้าพื้นที่ปลอดภัย (แจ้งตำรวจจราจรแล้ว)</div>';
            shouldBeep = true;

        } else if (st.risk_level === 'FALLEN') {
            cam1Box.classList.add('border-fallen');
            cam1Overlay.className = 'cam-alert-bar bar-fallen';
            cam1Overlay.style.display = 'block';
            cam1Overlay.textContent = 'FALLEN PERSON / พบผู้หมดสติล้มนอนบนทางเดิน (Zone2)';

            ledDot1.className = 'dot dot-fallen';
            ledScreen1.innerHTML =
                '<div class="led-title-fallen">EMERGENCY: FALLEN PERSON / พบผู้หมดสติล้มนอน</div>' +
                '<div class="led-desc">Area: <b style="color:var(--accent-vio);">[' + st.pole_id + ']</b> &mdash; ขอความช่วยเหลือปฐมพยาบาล (ประสานกู้ชีพ 1669 แล้ว)</div>';
            shouldBeep = true;

        } else if (st.risk_level === 'DANGER') {
            cam1Box.classList.add('border-danger');
            cam1Overlay.className = 'cam-alert-bar bar-danger';
            cam1Overlay.style.display = 'block';
            cam1Overlay.textContent = 'DANGER / อันตราย: ลำตัวช่วงล่างข้ามแนวราวสะพาน';

            ledDot1.className = 'dot dot-danger';
            ledScreen1.innerHTML =
                '<div class="led-title-danger">CRITICAL ALERT / แจ้งเตือนฉุกเฉิน: ขอความช่วยเหลือด่วน</div>' +
                '<div class="led-desc">High-risk: <b style="color:var(--accent-red);">[' + st.pole_id + ']</b> &mdash; ขอความร่วมมือผู้สัญจรเข้าพูดคุยช่วยเหลือ</div>';
            shouldBeep = true;

        } else if (st.risk_level === 'WARNING') {
            cam1Box.classList.add('border-warn');
            cam1Overlay.className = 'cam-alert-bar bar-warning';
            cam1Overlay.style.display = 'block';
            cam1Overlay.textContent = 'WARNING / เฝ้าระวัง: หัวไหล่ทั้ง 2 ข้างยื่นเข้าโซนราวสะพาน';

            ledDot1.className = 'dot dot-warn';
            ledScreen1.innerHTML =
                '<div class="led-title-warn">SAFETY ADVISORY / โปรดระมัดระวังความปลอดภัย</div>' +
                '<div class="led-desc">Area: <b style="color:var(--accent-amb);">[' + st.pole_id + ']</b> &mdash; กรุณาอย่าปีนป่ายราวสะพาน | สายด่วนสุขภาพใจ 1323</div>';

        } else {
            cam1Overlay.style.display = 'none';
            ledDot1.className = 'dot dot-ok';
            ledScreen1.innerHTML =
                '<div class="led-title-normal">RAMA 8 BRIDGE &mdash; ALL CLEAR / สถานะปกติ</div>' +
                '<div class="led-desc">Emergency / ฉุกเฉิน 1669 | Mental health / สุขภาพใจ 1323</div>';
        }

        // ==================== 2. อัปเดต CAM-02 & LED ช่องที่ 2 ====================
        const cam2Level = st2.risk_level || (st2.is_alert ? 'DANGER' : 'NORMAL');
        if (!isDrawingZone) {
            if (cam2Level === 'DANGER') {
                cam2Box.classList.add('border-danger');
                cam2Overlay.className = 'cam-alert-bar bar-danger';
                cam2Overlay.style.display = 'block';
                cam2Overlay.textContent = 'DEEPDETECT DANGER / พื้นที่เข้าโซน ' + Number(st2.max_pct || 0).toFixed(1) + '% (> 50%) | บันทึก VID แล้ว';

                ledDot2.className = 'dot dot-danger';
                ledScreen2.innerHTML =
                    '<div class="led-title-danger">CAM-02 DANGER / พื้นที่บุคคลล้ำโซนเกิน 50% (' + Number(st2.max_pct || 0).toFixed(1) + '%)</div>' +
                    '<div class="led-desc">Detected: <b style="color:var(--accent-red);">' + st2.person_count + ' Person(s)</b> &mdash; บันทึกหลักฐานวิดีโอแล้ว บริเวณ ' + st2.pole_id + '</div>';
                shouldBeep = true;
            } else if (cam2Level === 'WARNING') {
                cam2Box.classList.add('border-warn');
                cam2Overlay.className = 'cam-alert-bar bar-warning';
                cam2Overlay.style.display = 'block';
                cam2Overlay.textContent = 'DEEPDETECT WARNING / พื้นที่เข้าโซน ' + Number(st2.max_pct || 0).toFixed(1) + '% (30% - 50%)';

                ledDot2.className = 'dot dot-warn';
                ledScreen2.innerHTML =
                    '<div class="led-title-warn">CAM-02 WARNING / บุคคลเข้าใกล้โซนเฝ้าระวัง (' + Number(st2.max_pct || 0).toFixed(1) + '%)</div>' +
                    '<div class="led-desc">Detected: <b style="color:var(--accent-amb);">' + st2.person_count + ' Person(s)</b> &mdash; บริเวณ ' + st2.pole_id + '</div>';
            } else {
                cam2Overlay.style.display = 'none';
                ledDot2.className = 'dot dot-ok';
                ledScreen2.innerHTML =
                    '<div class="led-title-normal">ZONE 1 CLEAR / ไม่พบบุคคลในโซนเฝ้าระวัง</div>' +
                    '<div class="led-desc">Safe passage / ขอให้ทุกท่านเดินทางโดยสวัสดิภาพ</div>';
            }
        }

        // ==================== 3. อัปเดตกรอบรวม LED และ Global Badge ====================
        if (st.risk_level === 'VEHICLE') {
            ledWrapper.classList.add('lf-vehicle');
            globalBadge.className = 'status-ind si-vehicle';
            setBadgeContent(globalBadge, 'dot-vehicle', 'CAM-01 VEHICLE / รถยนต์รุกล้ำ' + (cam2Level !== 'NORMAL' ? ' + CAM-02 ' + cam2Level : ''));
        } else if (st.risk_level === 'FALLEN') {
            ledWrapper.classList.add('lf-fallen');
            globalBadge.className = 'status-ind si-fallen';
            setBadgeContent(globalBadge, 'dot-fallen', 'CAM-01 FALLEN / ผู้หมดสติ' + (cam2Level !== 'NORMAL' ? ' + CAM-02 ' + cam2Level : ''));
        } else if (st.risk_level === 'DANGER' || cam2Level === 'DANGER') {
            ledWrapper.className = 'status-ind si-danger';
            ledWrapper.classList.add('lf-danger');
            globalBadge.className = 'status-ind si-danger';
            setBadgeContent(globalBadge, 'dot-danger', 'DANGER / อันตราย (' + (st.risk_level === 'DANGER' ? 'CAM-01' : 'CAM-02 >50%') + ')');
        } else if (st.risk_level === 'WARNING' || cam2Level === 'WARNING') {
            ledWrapper.classList.add('lf-warn');
            globalBadge.className = 'status-ind si-warning';
            setBadgeContent(globalBadge, 'dot-warn', 'WARNING / เฝ้าระวัง (' + (st.risk_level === 'WARNING' ? 'CAM-01' : 'CAM-02 >=30%') + ')');
        } else {
            globalBadge.className = 'status-ind si-normal';
            setBadgeContent(globalBadge, 'dot-ok', 'NORMAL / ปกติทั้ง 2 กล้อง');
        }

        if (shouldBeep) playBeep();

        // ==================== 4. ตาราง Incident Log ====================
        const tbody = document.getElementById('log-table-body');
        if (data.logs.length > 0) {
            tbody.innerHTML = data.logs.map(row => {
                let tagClass = 'tag-warn';
                let dotClass = 'dot-warn';
                let tagLabel = row.risk_level;
                if (row.risk_level === 'DANGER')  { tagClass = 'tag-dang'; dotClass = 'dot-danger'; tagLabel = 'DANGER / อันตราย'; }
                if (row.risk_level === 'FALLEN')  { tagClass = 'tag-fall'; dotClass = 'dot-fallen'; tagLabel = 'FALLEN / ผู้หมดสติ'; }
                if (row.risk_level === 'VEHICLE') { tagClass = 'tag-veh';  dotClass = 'dot-vehicle'; tagLabel = 'VEHICLE / รถยนต์รุกล้ำ'; }
                if (row.risk_level === 'WARNING') { tagClass = 'tag-warn'; dotClass = 'dot-warn';   tagLabel = 'WARNING / เฝ้าระวัง'; }

                const isResolved = (row.status === '\u0e40\u0e02\u0e49\u0e32\u0e0a\u0e48\u0e27\u0e22\u0e40\u0e2b\u0e25\u0e37\u0e2d\u0e41\u0e25\u0e49\u0e27');
                const dataStatus = isResolved ? 'resolved' : 'pending';
                const statusColor = isResolved ? 'var(--accent-grn)' : 'var(--accent-red)';
                const statusLabel = isResolved ? 'RESOLVED / เข้าช่วยเหลือแล้ว' : 'PENDING / รอตรวจสอบ';

                const camName = row.camera_id ? row.camera_id : 'CAM-01';
                const poleWithCam = '<span class="cam-badge-inline">' + camName + '</span>' + (row.pole_id || '\u2014');

                const snapLink = row.snapshot_file
                    ? '<a class="btn" href="/captures/' + row.snapshot_file + '" target="_blank"><svg class="icon-svg" viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>IMG</a>'
                    : '';
                const vidLink = row.video_file
                    ? '<a class="btn" href="/captures/' + row.video_file + '" target="_blank"><svg class="icon-svg" viewBox="0 0 24 24"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg>VID</a>'
                    : '';

                return '<tr data-status="' + dataStatus + '">' +
                    '<td class="mono">' + String(row.id).padStart(4,'0') + '</td>' +
                    '<td class="mono">' + (row.timestamp || '\u2014') + '</td>' +
                    '<td><span class="tag ' + tagClass + '"><span class="dot ' + dotClass + '"></span>' + tagLabel + '</span></td>' +
                    '<td class="mono">' + poleWithCam + '</td>' +
                    '<td>' + (row.event_type || '\u2014') + '</td>' +
                    '<td>' + (snapLink + vidLink || '\u2014') + '</td>' +
                    '<td style="color:' + statusColor + ';font-weight:600;">' + statusLabel + '</td>' +
                    '<td>' + (isResolved ? '\u2014' : '<button class="btn btn-resolve" onclick="resolveIncident(' + row.id + ')"><svg class="icon-svg" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>CLOSE</button>') + '</td>' +
                '</tr>';
            }).join('');
            applyFilter();
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


@app.route("/api/get_zone_cam2", methods=["GET"])
def get_zone_cam2():
    return jsonify({"points": load_zone_points()})


@app.route("/api/set_zone_cam2", methods=["POST"])
def set_zone_cam2():
    data = request.get_json(silent=True) or {}
    points = data.get("points", [])
    if isinstance(points, list) and len(points) >= 3:
        save_zone_points(points)
        return jsonify({"ok": True, "points": points})
    return jsonify({"ok": False, "error": "Invalid points"}), 400


@app.route("/api/live", methods=["POST"])
def update_live():
    global latest_jpeg_frame, live_state
    live_state["risk_level"] = request.form.get("risk_level", "NORMAL")
    live_state["detected_parts"] = request.form.get("detected_parts", "None")
    live_state["hold_duration"] = to_float(request.form.get("hold_duration", 0.0))
    live_state["pole_id"] = request.form.get("pole_id", "เสา P8-N04 (ฝั่งพระนคร)")
    live_state["last_update"] = time.time()

    if "frame" in request.files:
        latest_jpeg_frame = request.files["frame"].read()
    return jsonify({"ok": True})


@app.route("/api/live_cam2", methods=["POST"])
def update_live_cam2():
    global latest_jpeg_frame_cam2, live_state_cam2
    risk_lvl = request.form.get("risk_level")
    is_alert_flag = request.form.get("is_alert") == "True"
    if not risk_lvl:
        risk_lvl = "DANGER" if is_alert_flag else "NORMAL"

    live_state_cam2["risk_level"] = risk_lvl
    live_state_cam2["is_alert"] = risk_lvl in ("WARNING", "DANGER")
    live_state_cam2["person_count"] = to_int(request.form.get("person_count", 0))
    live_state_cam2["max_pct"] = to_float(request.form.get("max_pct", 0.0))
    live_state_cam2["duration"] = to_float(request.form.get("duration", 0.0))
    live_state_cam2["pole_id"] = request.form.get("pole_id", "เสา P8-N04")
    live_state_cam2["last_update"] = time.time()

    if "frame" in request.files:
        latest_jpeg_frame_cam2 = request.files["frame"].read()
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


@app.route("/video_feed_cam2")
def video_feed_cam2():
    def generate():
        while True:
            if latest_jpeg_frame_cam2 is not None:
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n" + latest_jpeg_frame_cam2 + b"\r\n")
            time.sleep(0.06)
    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/api/incident", methods=["POST"])
def record_incident():
    data = request.get_json(silent=True) or {}
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
        to_float(data.get("duration", 0.0)),
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
    return jsonify({"live": live_state, "live_cam2": live_state_cam2, "logs": rows})


@app.route("/api/resolve/<int:inc_id>", methods=["POST"])
def resolve_incident(inc_id):
    global live_state, live_state_cam2
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE incident_logs SET status = 'เข้าช่วยเหลือแล้ว' WHERE id = ?", (inc_id,))
    conn.commit()
    conn.close()
    live_state["risk_level"] = "NORMAL"
    live_state_cam2["risk_level"] = "NORMAL"
    live_state_cam2["is_alert"] = False
    return jsonify({"ok": True})


@app.route("/api/reset_alert", methods=["POST"])
def reset_alert():
    global live_state, live_state_cam2
    live_state["risk_level"] = "NORMAL"
    live_state["hold_duration"] = 0.0
    live_state_cam2["risk_level"] = "NORMAL"
    live_state_cam2["is_alert"] = False
    live_state_cam2["duration"] = 0.0
    return jsonify({"ok": True})


@app.route("/captures/<path:filename>")
def serve_capture(filename):
    return send_from_directory(CAPTURE_DIR, filename)


if __name__ == "__main__":
    print("=== Bridge Smart Monitoring Server Running at http://127.0.0.1:8000 ===")
    app.run(host="0.0.0.0", port=8000, threaded=True)