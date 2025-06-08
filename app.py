#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import requests
import subprocess
import threading
import time
import signal
import shutil
import subprocess
import threading
import time
import signal
import shutil
from datetime import timedelta

try:
    import win32api  # type: ignore
except Exception:  # pragma: no cover - optional on non-Windows
    win32api = None

import cv2
import torch
from yt_dlp import YoutubeDL

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
with open(CONFIG_PATH, encoding="utf-8") as f:
    cfg = json.load(f)

CHANNEL_URLS = cfg.get("channels", [])
CHECK_INTERVAL = cfg.get("check_interval", 60)
OUTPUT_ROOT = os.path.join(BASE_DIR, cfg.get("output_folder", "recordings"))
EVIDENCE_ROOT = os.path.join(BASE_DIR, cfg.get("evidence_folder", "evidence"))
FFMPEG_EXE_NAME = cfg.get("ffmpeg_exe", "ffmpeg")
DETECT_MODEL = os.path.join(BASE_DIR, cfg.get("detect_model", "yolov5s.pt"))
CONF_THRESHOLD = float(cfg.get("conf_threshold", 0.5))
COOKIEFILE = cfg.get("cookiefile")
COOKIE_PATH = None
if COOKIEFILE:
    _cp = os.path.join(BASE_DIR, COOKIEFILE)
    if os.path.isfile(_cp):
        COOKIE_PATH = _cp
    else:
        print(f"[오류] 쿠키 파일을 찾을 수 없습니다: {_cp}")
        sys.exit(1)
LOG_MAX_SIZE = 10 * 1024 * 1024  # 10 MB per log file
# Logs from yt_dlp are stored as OUTPUT_ROOT/<channel>.log

ffmpeg_path = shutil.which(FFMPEG_EXE_NAME)
if not ffmpeg_path:
    ffmpeg_path = os.path.join(BASE_DIR, FFMPEG_EXE_NAME)
if not os.path.isfile(ffmpeg_path):
    print(f"[오류] ffmpeg 실행 파일을 찾을 수 없습니다: {FFMPEG_EXE_NAME}")
    print("config.json의 ffmpeg_exe 값을 확인하세요.")
    sys.exit(1)
EVIDENCE_ROOT = os.path.join(BASE_DIR, cfg.get("evidence_folder", "evidence"))
FFMPEG_EXE_NAME = cfg.get("ffmpeg_exe", "ffmpeg")
DETECT_MODEL = os.path.join(BASE_DIR, cfg.get("detect_model", "yolov5s.pt"))
CONF_THRESHOLD = float(cfg.get("conf_threshold", 0.5))
COOKIEFILE = cfg.get("cookiefile")
COOKIE_PATH = None
if COOKIEFILE:
    _cp = os.path.join(BASE_DIR, COOKIEFILE)
    if os.path.isfile(_cp):
        COOKIE_PATH = _cp
    else:
        print(f"[오류] 쿠키 파일을 찾을 수 없습니다: {_cp}")
        sys.exit(1)
LOG_MAX_SIZE = 10 * 1024 * 1024  # 10 MB per log file
# Logs from yt_dlp are stored as OUTPUT_ROOT/<channel>.log

ffmpeg_path = shutil.which(FFMPEG_EXE_NAME)
if not ffmpeg_path:
    ffmpeg_path = os.path.join(BASE_DIR, FFMPEG_EXE_NAME)
if not os.path.isfile(ffmpeg_path):
    print(f"[오류] ffmpeg 실행 파일을 찾을 수 없습니다: {FFMPEG_EXE_NAME}")
    print("config.json의 ffmpeg_exe 값을 확인하세요.")
    sys.exit(1)

stop_flag = False
recording_procs = {url: None for url in CHANNEL_URLS}
start_times = {}
detection_threads = {url: None for url in CHANNEL_URLS}
detector = None

def load_detector():
    model = torch.hub.load('ultralytics/yolov5', 'custom', path=DETECT_MODEL, force_reload=False)
    model.conf = CONF_THRESHOLD
    horse_ids = [i for i, n in model.names.items() if n.lower() == 'horse']

    def detect(frame):
        results = model(frame)
        for *_, conf, cls in results.xyxy[0]:
            if int(cls) in horse_ids and float(conf) >= CONF_THRESHOLD:
                return True
        return False

    return detect
def is_live_now(url):
    try:
        res = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=10)
        return 'isLiveNow' in res.text
    except requests.RequestException:
        return False

def start_recording(url):
    safe = url.split("@")[-1].split("/")[0]
    outd = os.path.join(OUTPUT_ROOT, safe)
    os.makedirs(outd, exist_ok=True)
    template = os.path.join(outd, "%(upload_date)s_%(title)s_%%03d.mp4")

    # Log file for this channel (stdout/stderr of yt_dlp)
    log_path = os.path.join(OUTPUT_ROOT, f"{safe}.log")
    mode = 'ab'
    if os.path.exists(log_path) and os.path.getsize(log_path) > LOG_MAX_SIZE:
        mode = 'wb'  # truncate when exceeding limit
    log_file = open(log_path, mode)

    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--ffmpeg-location", ffmpeg_path,
        "--no-part",  # ⭐️ part 파일 생성 방지
        "--external-downloader", "ffmpeg",
        "--external-downloader-args",
        "-c copy -f segment -segment_time 36000 -reset_timestamps 1 -segment_format mp4",
        "-f", "bestvideo+bestaudio",
        "-o", template,
        url
    ]
    if COOKIE_PATH:
        cmd.extend(["--cookies", COOKIE_PATH])
    if COOKIE_PATH:
        cmd.extend(["--cookies", COOKIE_PATH])
    proc = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT)
    proc.log_file = log_file  # store to close later
    start_times[url] = time.time()
    t = threading.Thread(target=detect_stream, args=(url, safe), daemon=True)
    t.start()
    detection_threads[url] = t
    return proc

def stop_recording(proc, url=None):
    if url and url in start_times:
        del start_times[url]
    t = detection_threads.get(url)
    if t and t.is_alive():
        t.join(timeout=1)
    detection_threads[url] = None
    if not proc:
        return
    for p in (proc if isinstance(proc, list) else [proc]):
        if p.poll() is None:
            p.send_signal(signal.SIGTERM)
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
        if hasattr(p, "log_file"):
            try:
                p.log_file.close()
            except Exception:
                pass

def create_evidence_writer(folder, base_name, fps, width, height):
    os.makedirs(folder, exist_ok=True)
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    path = os.path.join(folder, f"{base_name}_{timestamp}.mp4")
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(path, fourcc, fps, (width, height))
    return writer, path

def detect_stream(url, safe):
    global detector
    opts = {'quiet': True}
    if COOKIE_PATH:
        opts['cookiefile'] = COOKIE_PATH
    ydl = YoutubeDL(opts)
    try:
        info = ydl.extract_info(url, download=False)
    except Exception as e:
        print(f"[오류] 스트림 정보를 가져올 수 없습니다: {e}")
        if COOKIE_PATH:
            print("[안내] 쿠키 파일이 올바른지 확인하세요. Netscape 형식으로 최신 쿠키를 내보내야 합니다.")
        return
    opts = {'quiet': True}
    if COOKIE_PATH:
        opts['cookiefile'] = COOKIE_PATH
    opts = {'quiet': True}
    if COOKIEFILE:
        cookie_path = os.path.join(BASE_DIR, COOKIEFILE)
        if os.path.isfile(cookie_path):
            opts['cookiefile'] = cookie_path
    ydl = YoutubeDL(opts)
    try:
        info = ydl.extract_info(url, download=False)
    except Exception as e:
        print(f"[오류] 스트림 정보를 가져올 수 없습니다: {e}")
        return
    stream_url = info.get('url')
    cap = cv2.VideoCapture(stream_url)
    if not cap.isOpened():
        print(f"[오류] 스트림을 열 수 없습니다: {url}")
        return
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = None
    evidence_dir = os.path.join(EVIDENCE_ROOT, safe)
    while not stop_flag and url in start_times:
        ret, frame = cap.read()
        if not ret:
            break
        if detector and detector(frame):
            if writer is None:
                writer, path = create_evidence_writer(evidence_dir, safe, fps, width, height)
                print(f"[경고] {url} 말 감지 → 증거 녹화 시작: {path}")
            writer.write(frame)
        else:
            if writer:
                print(f"[경고] {url} 말 사라짐 → 증거 녹화 종료")
                writer.release()
                writer = None
    if writer:
        writer.release()
    cap.release()

def listen_for_exit():
    global stop_flag
    while True:
        if input().strip().lower() in ("exit", "quit", "q"):
            stop_flag = True
            break

def set_console_title(title):
    if win32api:
        win32api.SetConsoleTitle(title)

def show_elapsed():
    while not stop_flag:
        if start_times:
            parts = []
            for url, start in start_times.items():
                elapsed = int(time.time() - start)
                formatted_time = str(timedelta(seconds=elapsed))
                parts.append(f"{url.split('@')[-1].split('/')[0]} {formatted_time}")
            title_text = " | ".join(parts)
        else:
            title_text = "Waiting for streams..."
        set_console_title(title_text)
        time.sleep(1)

if __name__ == "__main__":
    print("────────────────────────────────────────")
    print(" 다중 채널 라이브 자동 녹화 스크립트 실행")
    print(f" 설정 파일: {CONFIG_PATH}")
    print(" 종료: exit, quit, q + Enter 또는 Ctrl+C")
    print("────────────────────────────────────────")

    detector = load_detector()

    os.makedirs(OUTPUT_ROOT, exist_ok=True)
    os.makedirs(EVIDENCE_ROOT, exist_ok=True)


    threading.Thread(target=listen_for_exit, daemon=True).start()
    threading.Thread(target=show_elapsed, daemon=True).start()

    try:
        while not stop_flag:
            for url in CHANNEL_URLS:
                proc = recording_procs[url]
                live = is_live_now(url)

                if live and proc is None:
                    print(f"\n[감지] {url} LIVE ON → 녹화 시작")
                    recording_procs[url] = start_recording(url)

                elif not live and proc:
                    print(f"\n[감지] {url} LIVE OFF → 녹화 중단")
                    stop_recording(proc, url)
                    recording_procs[url] = None

            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        stop_flag = True

    finally:
        print("\n[종료] 모든 녹화 중단")
        for url, proc in recording_procs.items():
            if proc:
                stop_recording(proc, url)
