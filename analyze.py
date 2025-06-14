#!/usr/bin/env python3
import os
import sys
import cv2
from yt_dlp import YoutubeDL
import torch
import time
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')
with open(CONFIG_PATH, encoding='utf-8') as f:
    cfg = json.load(f)

DETECT_MODEL = os.path.join(BASE_DIR, cfg.get('detect_model', 'yolov5s.pt'))
CONF_THRESHOLD = float(cfg.get('conf_threshold', 0.5))
EVIDENCE_ROOT = os.path.join(BASE_DIR, cfg.get('evidence_folder', 'evidence'))
COOKIEFILE = cfg.get('cookiefile')
COOKIE_PATH = None
if COOKIEFILE:
    _cp = os.path.join(BASE_DIR, COOKIEFILE)
    if os.path.isfile(_cp):
        COOKIE_PATH = _cp
    else:
        print(f'[오류] 쿠키 파일을 찾을 수 없습니다: {_cp}')
        sys.exit(1)


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


def create_writer(folder, base, fps, width, height):
    os.makedirs(folder, exist_ok=True)
    ts = time.strftime('%Y%m%d_%H%M%S')
    path = os.path.join(folder, f'{base}_{ts}.mp4')
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(path, fourcc, fps, (width, height))
    return writer, path


def analyze(url):
    opts = {'quiet': True}
    if COOKIE_PATH:
        opts['cookiefile'] = COOKIE_PATH
    ydl = YoutubeDL(opts)
    try:
        info = ydl.extract_info(url, download=False)
    except Exception as e:
        print(f'[오류] 동영상 정보를 가져오지 못했습니다: {e}')
        if COOKIE_PATH:
            print('[안내] 쿠키 파일이 올바른지 확인하세요. Netscape 형식으로 최신 쿠키를 내보내야 합니다.')
        return
    info = ydl.extract_info(url, download=False)
    stream_url = info['url']

    cap = cv2.VideoCapture(stream_url)
    if not cap.isOpened():
        print('[오류] 영상을 열 수 없습니다.')
        return
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    detector = load_detector()
    writer = None
    evidence_dir = os.path.join(EVIDENCE_ROOT, 'manual')

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if detector(frame):
            if writer is None:
                writer, path = create_writer(evidence_dir, 'evidence', fps, w, h)
                print(f'[경고] 말 감지 → 증거 녹화 시작: {path}')
            writer.write(frame)
        else:
            if writer:
                print('[경고] 말 사라짐 → 증거 녹화 종료')
                writer.release()
                writer = None
    if writer:
        writer.release()
    cap.release()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python analyze.py <youtube_url>')
        sys.exit(1)
    analyze(sys.argv[1])
