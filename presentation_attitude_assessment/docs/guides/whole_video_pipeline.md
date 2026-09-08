# 동영상 전체 시퀀스 처리

[문서 목차](../README.md)

`presentation-process`는 로컬 영상 파일 하나를 받아 첫 번째 비디오 스트림을 시작부터
FFmpeg EOF까지 처리한다. 별도의 샘플 목록이나 구간 계획은 필요하지 않다.
현재 결과는 모델에 전달할 특징 시퀀스이며, 태도 판정·학습·업로드 UI는 포함하지 않는다.

## 실행

저장소 루트에서 다음 명령을 실행한다. `video.mp4`는 실제 입력 경로로 바꾼다.

```sh
uv sync --locked
uv run --locked presentation-process /path/to/video.mp4 \
  --output .local-data/presentation-attitude/my-video \
  --fps 5 --window 3
```

출력 폴더는 새 경로여야 한다. 기본 모델은 기존 검증된 MediaPipe 모델 캐시를 공유하며,
파일이 없으면 고정된 명세에 따라 다운로드·해시 검증한다. `--models`와 `--model-specs`를
모두 지정하면 저장소 밖에 설치한 패키지에서도 기본 경로 탐색 없이 실행할 수 있다.

## 처리 흐름과 메모리

```text
영상 파일 → FFmpeg stdout → NumPy RGB 프레임 → MediaPipe 얼굴·손 좌표
         → 얼굴 기준 XY 정규화 → 구간별 중앙 이동평균 → sequence.jsonl
```

영상마다 얼굴·손 추적 세션을 한 번 열고 전체 프레임에서 이어 사용한다.
얼굴 crop이나 PNG 중간 저장·재읽기는 없다. Python 전처리는 이동평균 창 크기에
비례하는 좌표 버퍼만 유지하고, 완료한 레코드는 즉시 JSONL에 쓴다.
기본 창 3에서는 다음 샘플 1개를 기다린 뒤 현재 샘플의 결과를 내보낸다.
동일한 유효 구간 안에서 전체 창이 확보될 때만 평균을 내고, 결측·경계·영상 끝에서는
기존 정규화 좌표를 보존한다. 기존 작은 구간용 `preprocess()`는 여전히 리스트를 반환한다.

출력 파일 크기는 영상 길이에 비례한다. FFmpeg·MediaPipe 내부 메모리까지 고정된 크기라고
보장하지 않으며, 초장시간 영상의 메모리 사용량 벤치마크는 수행하지 않았다.

## 결과 형식

완료된 폴더에는 `summary.json`과 `sequence.jsonl`이 있다. JSONL 한 줄이 샘플 프레임 하나다.

| 필드 | 의미 |
|---|---|
| `raw.frame_index` | 영상 전체에서 0부터 시작하는 샘플 순번 |
| `raw.interval_timestamp_ms` | 영상 시작 기준 샘플 시각, 기존 구간 형식과 같은 필드명 |
| `raw.source_grid_seconds` | 샘플링 격자의 초 단위 시각 |
| `raw.face_landmarks`, `raw.hands` | 원시 XYZ와 얼굴·손 검출 정보 |
| `normalized_xy` | 얼굴 중심·크기로 정규화한 XY |
| `smoothed_xy` | 중앙 이동평균을 적용한 XY |
| `valid` | `face`, `Left`, `Right` 각각의 특징 사용 가능 마스크 |
| `missing_reason` | 검출 누락, 얼굴 기준점 부재, 손 좌우 불확실성 등 |
| `segment_id`, `smoothing_support` | 평균 적용 구간과 실제 사용 샘플 수 |
| `anchor` | 얼굴 기준점과 크기, 좌표 역변환에 사용 |

얼굴 478점, 손당 21점을 사용한다. 유효하지 않은 특징은 `null`이며 임의의 0으로
채우거나 해당 프레임을 삭제하지 않는다. `valid`는 관측 특징의 사용 가능 여부다.
가변 길이 배치의 padding 마스크는 모델 입력 단계에서 별도로 만든다.
z는 `raw`에만 보존한다. 원시 손 검출과 정규화된 좌우 슬롯은 의미가 다르다.

`summary.json`에는 입력·모델·구현·시퀀스 해시, FPS, 이미지 크기, 환경 버전,
프레임 수, 검출 수와 유효 특징 수, 완료 상태를 기록한다. 모든 특징이 누락된 영상도
디코딩이 정상 완료됐다면 `complete`, `has_valid_features=false`가 된다.
이는 분류할 수 있다는 뜻이 아니다. 현재 GRU 입력 단계는 모든 특징이 누락된 영상을 거부한다.

시각은 FFmpeg 재샘플링 격자이며 원본 프레임 PTS가 아니다.
`sampled_coverage_seconds=N/fps`와 `first_to_last_sample_seconds=(N-1)/fps`는
샘플 기준 값으로, 컨테이너의 정확한 재생 길이나 실제 얼굴 노출 시간과 같지 않다.
검출률을 실제 태도 라벨로 바꾸지 않는다.

## Python에서 사용

```python
from presentation_attitude.artifacts import iter_sequence
from presentation_attitude.pipelines.extraction import process_video

summary = process_video("/path/to/video.mp4", "new-output", fps=5, window=3)
for record in iter_sequence("new-output"):
    xy = record["smoothed_xy"]
    validity = record["valid"]
    timestamp_ms = record["raw"]["interval_timestamp_ms"]
```

`process_video()`는 요약 딕셔너리를 반환하고 좌표 전체는 파일에 보관한다.
`iter_sequence()`는 완료 상태와 파일 해시를 확인한 뒤 한 줄씩 읽는다.
전체 레코드를 `list()`로 모으지 않으면 읽기 단계도 영상 길이에 비례해 메모리를 늘리지 않는다.

## 실패와 검증

진행 중에는 `sequence.jsonl.partial`에 기록하고, 요약을 100프레임마다 갱신한다.
정상 EOF와 저장 완료 후에만 `sequence.jsonl`로 바꾸고 `complete`로 표시한다.
처리 오류·Ctrl+C는 `failed`로 기록하며 프로세스와 추적 세션을 닫는다.
강제 종료·전원 중단으로 상태가 `running`에 남아도 `iter_sequence()`는 이를 거부한다.
부분 결과 이어쓰기는 지원하지 않으므로 재실행할 때 새 출력 경로를 사용한다.

자동 테스트는 중앙 창·결측 경계·EOF·점진적 입력 소비를 확인한다. 생성한 임시 영상을
실제 FFmpeg로 읽고, 가짜 검출기를 이용해 전체 프레임 보존·실패 시 자원 정리·미완료
결과 거부·파일 변조 검출을 검사한다. 실제 MediaPipe 검증은 별도로 기록한다.

실측: 비전 테스트 32개와 데이터 합성 테스트 4개가 통과했다. 실제 MediaPipe로
짧은 영상 전체 9프레임과 의회 발언 영상 전체 1,317프레임을 처리했다.
저장된 모든 레코드의 시각·좌표 형태·유한 값·결측 마스크·파일 해시·프레임 수를 확인했다.
기존 MIT 700프레임의 전처리와 짧은 영상 9프레임의 새 출력은 이전 결과와 바이트 단위로 같다.
[검증 기록](../history/whole_video_results.json)에 실행 경로와 해시를 남겼다.
의회 영상의 태도 적합성 검토·라벨링이나 분류 성능 검증을 완료한 것은 아니다.
