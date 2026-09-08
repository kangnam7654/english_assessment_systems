# FFmpeg → NumPy 스트리밍 입력

[문서 목차](../README.md)

`src/presentation_attitude/vision/video.py`의 `FFmpegVideoReader`가 로컬 동영상을 한 프레임씩 전달한다.
영상이나 프레임 파일을 중간에 저장하지 않는다. `presentation-audit`의 기본 입력 경로다.

```python
from presentation_attitude.vision.video import FFmpegVideoReader

with FFmpegVideoReader(
    "video.mp4", fps=5, start_seconds=10, duration_seconds=20
) as video:
    for index, rgb in enumerate(video):
        # rgb: RGB 순서, uint8, (height, width, 3), C-contiguous
        # 바로 mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)에 전달
        timestamp_ms = round(index * 1000 / video.fps)
```

저장소 루트에서 `uv sync --locked` 후 공통 환경의 Python으로 import한다.
`duration_seconds`를 생략하면 지정한 시작 시점부터 파일 끝까지 읽는다.

## 처리·수명 규칙

1. ffprobe로 첫 비디오 스트림의 크기와 회전 정보를 확인한다.
2. `subprocess.Popen`으로 FFmpeg를 실행한다. FFmpeg가 디코딩·회전·fps 샘플링 후
   `rgb24` rawvideo를 stdout 파이프에 쓴다.
3. 한 프레임에 필요한 `width × height × 3`바이트를 모아
   `np.frombuffer(..., dtype=np.uint8).reshape(height, width, 3)`로 전달한다.
4. EOF, 소비자 예외, `with` 안의 조기 `break`에서 파이프를 닫고 프로세스를 회수한다.
   반드시 `with` 블록으로 사용한다. 객체는 한 번만 사용할 수 있다.

반환 배열은 각 프레임의 독립적인 불변 bytes를 참조한다. 다음 프레임을 읽거나 reader를
닫아도 기존 배열은 유지된다. 수정하려면 `rgb.copy()`를 사용한다. reader는 전체 영상을
메모리에 모으지 않는다. audit 도구는 별도로 좌표 레코드와 소수의 미리보기 프레임을 보관한다.

stderr는 별도 스레드로 계속 읽고 마지막 최대 64KiB만 보존한다. 로그가 많이 발생해도
stderr 파이프가 차서 디코딩을 막지 않도록 했다. 비정상 종료, 프레임 중간 EOF,
샘플 프레임이 없는 구간은 성공적인 빈 데이터로 처리하지 않고 오류를 낸다.

회전 메타데이터는 90도 단위를 지원한다. rawvideo에는 프레임별 크기 헤더가 없으므로
출력 크기는 첫 스트림의 회전 반영 크기로 고정한다. 고정 해상도 입력에서는 scale 필터가
동일 크기를 유지한다. 중간 해상도가 달라지는 영상은 그 크기로 맞추며 별도 실영상 검증은 하지 않았다.
시각은 재샘플링 격자 기준이다. 원본 프레임의 정확한 PTS는 제공하지 않는다.

## 진단용 저장

기본 실행에는 `frames/`와 PNG가 없다. MediaPipe에 NumPy 배열을 직접 넣은 뒤,
선택한 소수 프레임을 메모리에서 그려 `contact_sheet.jpg`를 만든다.
`--save-frames`를 지정하면 추론 후 진단용 PNG 사본도 저장한다. 저장한 사본을 추론에
다시 읽어 넣는 경로는 없다. 전체 비교 영상이 필요한 경우에만 이 옵션을 사용한다.

전처리는 새 summary의 `width`, `height`를 사용하므로 PNG가 없어도 실행된다.
과거 summary에는 크기가 없으므로 예전 결과를 읽을 때에만 기존 첫 PNG를 참조한다.
`presentation-render`의 전체 비교 영상 생성에는 진단 PNG가 필요하다.

## 검증 기록 (2026-09-07)

- 테스트 25개 통과: RGB 순서·배열 수명, seek·5fps 샘플링, 부분 pipe read,
  프레임 절단, 빈 출력, 잘못된 입력, 큰 stderr와 종료 오류, 조기 중단·예외 정리,
  90도 회전 메타데이터를 포함한다.
- MIT 7구간의 RGB **700/700프레임이 기존 PNG 경로와 픽셀 단위로 동일**했다.
- 새 추출과 전처리는 `cv2.imread` 호출 시 실패하도록 막은 상태에서 완료됐다.
  PNG는 0개였고, 원시 랜드마크 700개와 전처리 레코드 700개 모두 기존 결과와
  바이트 단위로 같았다. 기존 검출 누락·오검출도 그대로이며 정확도 개선 작업은 아니다.
- `--save-frames`는 별도 9프레임 구간에서 추론의 이미지 읽기를 막은 상태로 검증했다.
- 실제 속도·최대 메모리 벤치마크는 수행하지 않았다. PNG 인코딩·저장·재읽기를 생략하는
  구조적 변경과 측정한 성능 향상을 구분한다. RTX 5090 실행은 미검증이다.

[검증 메타데이터](../history/ffmpeg_streaming_results.json)에 경로·해시·대조 결과를 기록했다.
기존 [MIT 연속 검증](../history/mit_continuity_review.md)은 PNG 경로에서 얻었던 과거 기록으로 보존한다.

구현 근거: [FFmpeg rawvideo 형식](https://ffmpeg.org/ffmpeg-formats.html#rawvideo),
[FFmpeg pipe 프로토콜](https://ffmpeg.org/ffmpeg-protocols.html#pipe),
[NumPy frombuffer](https://numpy.org/doc/stable/reference/generated/numpy.frombuffer.html).
