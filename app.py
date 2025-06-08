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
import win32api
from datetime import timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
with open(CONFIG_PATH, encoding="utf-8") as f:
    cfg = json.load(f)

CHANNEL_URLS = cfg.get("channels", [])
CHECK_INTERVAL = cfg.get("check_interval", 60)
OUTPUT_ROOT = os.path.join(BASE_DIR, cfg.get("output_folder", "recordings"))
FFMPEG_EXE_NAME = cfg.get("ffmpeg_exe", "ffmpeg.exe")

ffmpeg_path = os.path.join(BASE_DIR, FFMPEG_EXE_NAME)
if not os.path.isfile(ffmpeg_path):
    print(f"[오류] ffmpeg.exe를 찾을 수 없습니다: {ffmpeg_path}")
    sys.exit(1)

stop_flag = False
recording_procs = {url: None for url in CHANNEL_URLS}
start_times = {}

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
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    start_times[url] = time.time()
    return proc

def stop_recording(proc, url=None):
    if url and url in start_times:
        del start_times[url]
    if not proc:
        return
    for p in (proc if isinstance(proc, list) else [proc]):
        if p.poll() is None:
            p.send_signal(signal.SIGTERM)
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()

def listen_for_exit():
    global stop_flag
    while True:
        if input().strip().lower() in ("exit", "quit", "q"):
            stop_flag = True
            break

def set_console_title(title):
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
