# Horse Detecting Multi Recorder

이 스크립트는 여러 유튜브 채널의 라이브 방송을 자동으로 감지해 녹화하고
실시간으로 말 객체를 탐지하여 별도의 채증 영상을 저장합니다.

## 로그 확인

채널별 `yt_dlp` 실행 로그는 `recordings/<채널이름>.log` 파일에 기록됩니다.
로그 크기가 10MB를 초과하면 자동으로 덮어쓰며 새로운 내용이 저장됩니다.

예) `recordings/mychannel.log`

녹화 중 문제가 발생했는지 확인하고 싶을 때 해당 로그 파일을 열어보세요.

## 폴더 구조

일반 녹화물은 `recordings/` 폴더에,
말 감지 시 저장되는 증거 영상은 `evidence/` 폴더에 구분되어 저장됩니다.

## 수동 분석

`analyze.py` 스크립트를 이용하면 원하는 유튜브 영상 링크를 입력해
동일한 말 탐지 로직을 적용할 수 있습니다.

```
python analyze.py <youtube_url>
```

