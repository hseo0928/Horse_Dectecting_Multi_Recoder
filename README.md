# Horse Detecting Multi Recorder

이 스크립트는 여러 유튜브 채널의 라이브 방송을 자동으로 감지해 녹화합니다.

## 로그 확인

채널별 `yt_dlp` 실행 로그는 `recordings/<채널이름>.log` 파일에 기록됩니다.
로그 크기가 10MB를 초과하면 자동으로 덮어쓰며 새로운 내용이 저장됩니다.

예) `recordings/mychannel.log`

녹화 중 문제가 발생했는지 확인하고 싶을 때 해당 로그 파일을 열어보세요.

