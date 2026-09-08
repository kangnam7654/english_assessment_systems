# 발표 태도 평가 시스템 — 문서 읽기 안내

처음에는 아래 세 문서만 읽으면 됩니다. 나머지는 필요한 내용을 찾을 때 참고하세요.

1. **[코드 구조](guides/python_structure.md)** — 폴더별 역할과 모델·데이터·파이프라인의 관계.
2. **[영상 처리 흐름](guides/whole_video_pipeline.md)** — 영상 하나가 어떤 과정을 거쳐 특징 시퀀스가 되는지.
3. **[서빙 실행](guides/serving.md)** — FastAPI와 분석 워커를 실행하고 결과를 조회하는 방법.

## 현재 시스템 한눈에 보기

```text
영상 업로드 → FastAPI 접수 → SQLite 작업 대기 → 분석 워커
                                               │
                 FFmpeg → MediaPipe → 좌표 정규화·이동평균
                                               │
                         특징 시퀀스 → 선택적 GRU → 결과 저장
                                               │
                                 FastAPI 상태·결과 조회
```

로컬 영상 처리·학습·평가 파이프라인·API와 별도 워커가 구현돼 있습니다.
기본 서빙은 **특징 추출**이며 실제 태도 라벨 데이터와 검증된 분류 모델은 아직 없습니다.
합성 좌표로 학습 흐름을 검증한 결과를 실제 발표 태도 정확도로 해석하지 않습니다.

API 기본 주소는 `http://127.0.0.1:43187`입니다. 실행 명령은 서빙 안내에 있습니다.

## 궁금한 내용으로 찾기

| 궁금한 내용 | 읽을 문서 |
|---|---|
| 당시 크레버스 업무와 이번 재구현은 어떻게 다른가? 태도 라벨 기준은? | [재구현·라벨링 기준](guides/presentation_attitude.md) |
| 코드는 어디에 있고 어떻게 import하는가? | [코드 구조](guides/python_structure.md) |
| 영상 전체에서 무엇을 추출하고 어떤 파일을 저장하는가? | [영상 처리 흐름](guides/whole_video_pipeline.md) |
| FFmpeg의 바이트를 어떻게 NumPy로 받는가? | [FFmpeg 스트리밍 상세](guides/ffmpeg_streaming.md) |
| 거리 정규화·이동평균·결측 처리는 어떻게 하는가? | [전처리 상세](guides/preprocessing.md) |
| GRU 입력과 학습 방법은 무엇인가? | [GRU 학습](guides/gru_training.md) |
| 저장한 모델의 정확도·F1과 오분류를 어떻게 확인하는가? | [모델 성능 평가](guides/evaluation.md) |
| 영상 업로드·분석 결과 화면을 직접 사용하려면? | [추론 UI](../frontend/README.md) |
| API 서버와 분석 워커를 어떻게 실행하는가? | [서빙 실행](guides/serving.md) |
| 프런트엔드가 주고받을 필드와 오류는 무엇인가? | [API 명세](guides/api_contract.md) |

## 데이터가 필요할 때

`data/`에는 데이터 조사 기록과 목록·주석 양식이 있습니다. 영상 파일 자체는 없습니다.

- [후보 데이터 검토](data/data_review.md): 자료의 성격과 목표 태도 평가의 차이.
- [접근·이용 조건 검토](data/data_access_review.md): 파일별 조사 근거. 2026-09-07 확인 기록입니다.
- [샘플 목록](data/sample_inventory.json): 파일명·출처·해시·로컬 경로. audit CLI가 읽는 입력이기도 합니다.
- [주석 템플릿](data/annotation_template.json): 실제 영상을 검토할 때 작성할 양식.
- [접근 조사 원본 JSON](data/data_access_review.json): 세부 증거를 확인할 때만 참고합니다.

## 과거 검증 결과가 필요할 때

**[실험·검증 기록 목차](history/README.md)**에서 보고서와 실행 결과 JSON을 찾을 수 있습니다.
시스템을 이해하거나 실행하기 위해 이 기록들을 모두 읽을 필요는 없습니다.
검증 문서에 적힌 테스트 수·Python 버전·후속 작업은 해당 실행 시점의 기록입니다.
가이드 안의 과거 실측·검증 항목도 같은 기준으로 읽습니다.

```text
docs/
├── README.md    # 지금 읽고 있는 시작점
├── guides/     # 설계·코드 구조·사용법
├── data/       # 데이터 조사·샘플 목록·주석 양식
└── history/    # 과거 실험 보고서·실행 결과 JSON
```

개발 명령과 프로젝트 전체 안내는 [모듈 README](../README.md)에 있습니다.
