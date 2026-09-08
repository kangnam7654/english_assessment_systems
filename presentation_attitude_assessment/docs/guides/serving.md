# FastAPI와 별도 분석 워커

[문서 목차](../README.md)

요청·응답 필드, HTTP 오류, 재시도 및 화면 연결 규칙은 [API 명세](api_contract.md)에 정리했다.

같은 컴퓨터에서 API 서버와 분석 워커를 별도 Python 프로세스로 실행한다.
API는 업로드·상태·결과 조회를 담당하고 Torch나 MediaPipe를 import하지 않는다.
워커 하나가 SQLite 큐에서 영상을 순서대로 가져와 기존 FFmpeg → MediaPipe →
정규화·이동평균 → 선택적 GRU 추론 파이프라인을 실행한다.

현재 실제 태도 라벨로 학습한 체크포인트는 없다. 기본 `features` 모드는 영상 전체의
특징 추출 결과를 반환하며 `assessment`는 `null`이다. 검출 비율은 태도 점수가 아니다.

## 실행

저장소 루트에서 공통 환경을 동기화한다. FFmpeg·ffprobe도 PATH에 있어야 한다.

```sh
uv sync --locked
```

첫 번째 터미널에서 API를 시작한다.

```sh
uv run --locked presentation-serve
```

두 번째 터미널에서 워커를 시작한다.

```sh
uv run --locked presentation-worker
```

API는 `127.0.0.1:43187`에 열린다. `http://127.0.0.1:43187/docs`의
`POST /jobs` → Try it out에서 영상을 선택해 업로드할 수 있다.
이 모듈의 기본 포트는 `43187`로 정했다. 다른 프로세스가 사용 중이면
`presentation-serve --port 43188`처럼 변경할 수 있다. 자동으로 다른 포트를 선택하지 않는다.
반환된 `status_url`을 조회하고 `succeeded`가 되면 `result_url`을 조회한다.
`/docs`는 API 확인용 화면이다. 사용자용 영상 업로드·결과 UI는
[프런트엔드 실행 안내](../../frontend/README.md)에 따라 빌드하면 같은 서버의 `/ui/`에서 사용할 수 있다.

두 프로세스는 기본적으로 `.local-data/serving`을 공유한다. 위치를 바꿀 때는
두 터미널에 같은 절대 경로의 `PAA_DATA_DIR`를 설정한다.

```sh
export PAA_DATA_DIR=/absolute/path/to/local-serving-data
```

| API | 동작 |
|---|---|
| `GET /health` | API와 SQLite 접근 확인. 워커 생존 여부는 확인하지 않음 |
| `POST /jobs?mode=features` | multipart `file` 업로드. 저장 완료 후 HTTP 202·작업 ID 반환 |
| `POST /jobs?mode=assessment` | 같은 입력으로 태도 추론 요청. 워커에 체크포인트가 없으면 실패 |
| `GET /jobs/{id}` | 현재 상태·시도 번호·시도별 오류·상태 및 결과 URL |
| `GET /jobs/{id}/result` | 성공한 마지막 시도의 결과. 미완료·실패는 HTTP 409 |
| `POST /jobs/{id}/retry` | 실패한 작업만 다시 큐에 등록. 이전 시도 기록 보존 |

상태는 `queued → running → succeeded / failed`로 바뀐다. 워커가 꺼져 있으면
업로드된 작업은 `queued`로 남는다. 상태 조회는 단계 기준이며 프레임별 진행률은 없다.

## 데이터와 중단 처리

```text
PAA_DATA_DIR/
  jobs.sqlite3           # WAL 모드; 작업 및 시도별 결과를 트랜잭션으로 저장
  worker.lock            # 단일 워커를 보장하는 OS 파일 잠금
  jobs/<server UUID>/
    source.video         # 사용자 파일명을 경로로 사용하지 않음
    attempt-1/           # 기존 pipelines/extraction.py 산출물
      summary.json
      sequence.jsonl
    attempt-2/           # 재시도는 새로운 디렉터리 사용
```

- 업로드 완료 후 큐에 등록한다. 빈 파일·허용하지 않은 확장자·크기 초과는 거절한다.
  파일 크기 기본 제한은 256 MiB이며 `PAA_MAX_UPLOAD_BYTES`로 변경할 수 있다.
  multipart 전체 본문도 파일 제한 + 64 KiB로 제한해 임시 저장을 제한한다.
- 실제 디코딩 검증은 워커가 수행한다. MP4/MOV, Matroska/WebM, AVI demuxer와
  로컬 file/pipe 프로토콜만 허용한다. 원격 플레이리스트는 입력으로 받지 않는다.
- 최대 디코딩 픽셀 수는 3840 × 2160, 최대 샘플 프레임 수는 10,000이다.
  워커의 `PAA_MAX_FRAMES`로 프레임 제한을 바꿀 수 있다. 초과 시 부분 영상 판정을
  반환하지 않고 실패한다. 5 FPS에서 10,000프레임은 약 33분 20초에 해당한다.
- 워커는 저장된 원본 SHA-256을 확인하고 작업을 가져온다. SQLite의 원자적 claim과
  실행 시도 번호 검증으로 중복 claim 및 오래된 시도의 결과 덮어쓰기를 방지한다.
- 단일 워커 잠금은 macOS/Linux의 `flock`을 사용한다. 두 번째 워커는 기존 작업을
  변경하기 전에 종료된다. 잠금 파일 자체는 지우지 않는다.
- SIGINT/SIGTERM은 분석 문맥을 정리하고 현재 시도를 실패 처리한다. SIGKILL처럼
  정리할 수 없는 종료 후에는 **다음 워커 시작 때** 남은 `running` 작업을
  `worker_interrupted`로 실패 처리한다. 자동으로 무한 재시도하지 않는다.
  API 재시작만으로 실행 중 작업을 실패 처리하지 않는다.
- 원본 영상·특징·시도 기록을 자동 삭제하지 않는다. 프로세스 강제 종료가 업로드의
  파일 저장과 DB 등록 사이에 발생하면 큐에 없는 파일이 남을 수 있다.

## 모델 수명과 판정 모드

워커가 시작될 때 `VideoAnalyzer`를 한 번 만든다. 체크포인트를 설정했다면 이때
`ClassifierRuntime`이 GRU를 로드하고 후속 영상에서 재사용한다. GRU hidden state는
영상 간 공유하지 않는다. MediaPipe Tasks는 영상당 하나의 VIDEO 추적 세션을 만들고
그 영상의 프레임 동안 재사용한 뒤 닫는다. 영상 간 MediaPipe 모델 객체 재사용은
아직 구현하지 않았다.

추후 `purpose=attitude_training`, `0=inappropriate`, `1=appropriate`인 체크포인트를
준비하면 다음처럼 워커에 연결한다. 체크포인트 파일은 운영자가 지정하며 업로드 API로
받지 않는다.

```sh
uv run --locked presentation-worker --checkpoint /path/to/best.pt --device cpu
```

`pipeline_smoke` 체크포인트는 시작 시 거절한다. FPS·이동평균 window는 체크포인트에서
읽으며 전체 특징 설정과 모델 자산은 기존 `ClassifierRuntime`의 일치 검증을 거친다.
모든 특징이 누락된 영상은 `unavailable`이며 부적절한 태도로 판정하지 않는다.
판정 임계값 0.5는 초기 고정값이다. 실제 데이터 정확도와 확률 보정은 검증되지 않았다.

## 코드 구성과 검증 범위

| 코드 | 책임 |
|---|---|
| `serving/settings.py` | 공통 경로와 제한값 |
| `serving/api.py` | 업로드 제한·접수·상태·결과·재시도 |
| `serving/contracts.py` | 작업 저장소 인터페이스·상태 충돌 오류·단일 워커 복구 계약 |
| `serving/store.py` | 인터페이스의 SQLite 구현: 상태 전이·시도 기록·접근 확인 |
| `serving/files.py` | DB와 독립적인 로컬 작업 파일 경로 |
| `serving/worker.py` | 단일 워커 잠금·중단 복구·작업 실행 |
| `serving/analyzer.py` | 기존 영상 파이프라인과 선택적 GRU 연결 |
| `cli/serve.py`, `cli/worker.py` | 두 프로세스의 독립 실행 명령 |

기존 공통 Python 3.13 환경을 사용한다. FastAPI·Uvicorn을 비전 패키지의 직접
의존성으로 선언했고, 새 설치 패키지는 `python-multipart` 하나다.
검증 내역은 [serving_results.json](../history/serving_results.json)에 기록한다.

이번 범위는 로컬 기능 검증이다. 인증·공개 배포·GPU 실행·다중 워커·네트워크 파일시스템·
자동 보존 기간·분석 제한 시간은 구현/검증하지 않았다. 로컬의 신뢰할 수 있는 영상으로
실행하며 CLI는 루프백에만 바인딩한다. 장시간 멈춘 디코더를 강제로 종료해야 한다면
워커 종료 후 재시작으로 복구할 수 있다. Windows 네이티브 실행은 지원하지 않는다.

FastAPI의 multipart 파일 업로드 방식은
[공식 문서](https://fastapi.tiangolo.com/tutorial/request-files/)를 참고했다.


## 확장성을 위한 경계

현재는 SQLite와 단일 로컬 워커를 유지한다. API와 `JobWorker`는 `JobRepository`의
작업 등록·조회·claim·완료·재시도·상태 확인 메서드를 사용한다. SQL과 연결 관리는
`JobStore` 안에만 있다. `create_app(..., store_factory=...)`와
`run_worker(..., store_factory=...)`로 저장소 구현을 주입할 수 있으며 기본값은 SQLite다.
CLI와 환경 변수에 미구현 백엔드 선택지는 추가하지 않았다.

`LocalJobFiles`는 작업 파일 경로를 담당한다. DB와 파일 저장 위치를 분리할 수 있지만,
API의 파일 쓰기와 분석기의 입력은 여전히 로컬 파일을 사용한다. 원격 객체 저장소 어댑터는 아니다.
기본 DB 스키마, 디렉터리 배치, HTTP 응답 형식과 모델 수명은 동일하다.
직접 `JobWorker`를 사용하는 Python 코드는 `files=LocalJobFiles(data_dir)`도 전달한다.
이전 `JobStore.job_dir()` 호출은 이 파일 관리 객체의 `job_dir()`로 옮긴다.

| 확장 상황 | 추가로 구현·검증할 내용 |
|---|---|
| 다른 DB 사용 | `JobRepository` 구현, 기존 작업·시도 데이터 마이그레이션, 트랜잭션·동시 claim·오래된 완료 거절 검증 |
| 여러 워커 사용 | 작업별 소유권·유효 기간(lease), heartbeat, 만료된 작업만 복구, 이전 워커의 결과 저장 거절 |
| API와 워커를 다른 서버에 배치 | 원본·특징의 공유 저장소, 워커의 다운로드·업로드 단계, 저장 완료 확인 뒤 작업/결과 공개 |
| 별도 메시지 큐 도입 | DB 등록과 메시지 발행 사이 유실 방지, 중복 전달 시 같은 작업을 안전하게 처리, 재시도 일관성 |

`claim()`은 대기 작업 선택과 시도 번호 증가를 원자적으로 수행해야 한다. `finish()`는
현재 실행 중인 시도만 완료시킬 수 있어야 하고, `retry()`는 기존 시도 기록을 보존해야 한다.
새 저장소도 이 동작과 기존 HTTP 결과를 유지하는 계약 테스트를 통과해야 한다.
메시지 큐는 나중에 필요할 때 추가하며, 지금부터 DB와 큐를 동시에 운영하지 않는다.

현재 `run_worker`는 단일 워커 전용이다. `LocalWorkerRepository.recover_interrupted()`가
모든 `running` 작업을 실패 처리하므로 **파일 잠금만 제거해서 여러 워커를 실행하면 안 된다.**
사용자 정의 저장소 팩토리를 주입하더라도 같은 저장소를 쓰는 모든 실행은 같은
`settings.data_dir`의 단일 잠금을 공유해야 한다. 여러 서버에서는 이 파일 잠금 대신
작업별 소유권과 만료 조건에 맞춘 별도 실행·복구 경로가 필요하다.

2026-09-08: 기본 SQLite 동작, 프로세스 중단 복구, 동시 claim, 오래된 완료 거절을 포함해
비전 테스트 69개와 Ruff 검사·포맷 검사가 통과했다. 추가한 통합 테스트에서는 SQL 연결이나
파일 경로 메서드를 노출하지 않는 저장소 객체를 주입하고, DB와 파일 폴더를 분리한 채
업로드 → 실패 → 재시도 → 성공 → API 재시작 후 조회를 확인했다.
이는 의존 경계의 검증이며 다른 DB·원격 저장소·다중 워커의 실제 구현 검증은 아니다.
