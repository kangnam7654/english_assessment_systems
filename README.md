# English Assessment Systems

[English](README.en.md)

**발표 영상 분석부터 영어 쓰기·음성 인식까지, 평가 업무의 재구현.**

크레버스에서 수행했던 업무를 다시 구현하는 포트폴리오 모노레포입니다.
각 프로젝트는 독립적으로 살펴볼 수 있으며 애플리케이션 Python 환경을 공유합니다. GPU 학습용 CUDA 환경은 별도로 관리합니다.
회사 코드·내부 데이터·학습 가중치는 포함하지 않습니다.

## 프로젝트

### [발표 태도 평가 →](presentation_attitude_assessment/README.md)

영상에서 얼굴·손의 움직임을 추출하고, 랜드마크 시퀀스를 전처리해 작은 분류 모델을
학습합니다. 평가 코드와 분석 워커를 연결한 로컬 업로드 API도 포함합니다.

**MediaPipe · FFmpeg · PyTorch · FastAPI**

파이프라인은 구현됐으며, 검증된 태도 분류 모델을 위해 실제 라벨 데이터가 필요합니다.

### [영어 쓰기 데이터 합성 →](writing_data_synthesis/README.md)

학년·수준에 맞는 에세이를 생성하고, LangGraph 워크플로를 통해 루브릭에 따라
평가합니다. API와 Next.js 데모를 포함합니다.

**LangGraph · Ollama · FastAPI · Next.js**

출력은 합성 데이터 후보입니다. 사람의 검수와 배치 데이터셋 내보내기는 후속 작업입니다.

### [아동 영어 음성 인식 →](child_speech_recognition/README.md)

한국 아동의 영어 음성에 맞춰 Parakeet을 파인튜닝했습니다.
NeMo 학습으로 고정 Test WER를 **14.45% → 8.50%**로 낮췄습니다.
실험 결과·전사 비교와 로컬 음성 청취 예시 생성 코드를 포함합니다.

**NVIDIA NeMo · Parakeet TDT · PyTorch · AI Hub**

현재 재구현의 평가 결과이며 당시 회사 시스템의 성능은 아닙니다.
원본 음성·정답 라벨·가중치는 재배포하지 않습니다.

## 시작하기

저장소 루트에서:

```sh
uv sync --locked
```

발표 태도 평가와 쓰기 데이터 합성 프로젝트는 **Python 3.13**과 루트 `uv.lock`을 공유합니다.
실행 방법은 위 프로젝트별 README에 있습니다.

[Python 설치·의존성 안내](docs/python_environment.md) ·
[MIT License](LICENSE)

외부 영상에는 원본의 이용 조건이 적용됩니다.
