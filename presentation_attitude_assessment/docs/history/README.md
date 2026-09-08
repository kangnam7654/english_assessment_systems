# 실험·검증 기록

[문서 목차](../README.md)

문제가 재발했을 때 이전 결과와 대조하거나, 포트폴리오 설명의 근거를 확인하는 기록입니다.
각 파일의 시각·환경·검증 범위를 기준으로 읽습니다. 아래 순서는 구현 단계 순서입니다.

| 단계 | 읽을 보고서 | 원본 결과 |
|---|---|---|
| 초기 얼굴·손 추출 및 수동 crop 진단 | [초기 추출 검증](landmark_audit.md) | [추출 JSON](audit_results.json) |
| 좌표 정규화·이동평균 | [전처리 가이드의 실측 항목](../guides/preprocessing.md#실제-실행) | [전처리 JSON](preprocessing_results.json) |
| MIT 강연 7구간·700프레임 검증 | [MIT 연속 검증](mit_continuity_review.md) | [추출](mit_audit_results.json) · [전처리](mit_preprocessing_results.json) · [연속성](mit_continuity_results.json) |
| FFmpeg stdout → NumPy 입력으로 전환 | [스트리밍 가이드의 검증 항목](../guides/ffmpeg_streaming.md) | [스트리밍 JSON](ffmpeg_streaming_results.json) |
| 프로젝트 폴더·공통 환경 정리 | [모듈 README](../../README.md) | [구조 변경 JSON](structure_results.json) |
| 영상 하나 전체 처리 | [전체 영상 가이드의 검증 항목](../guides/whole_video_pipeline.md#실패와-검증) | [전체 영상 JSON](whole_video_results.json) |
| GRU 합성 좌표 학습 | [GRU 가이드의 검증 항목](../guides/gru_training.md#검증-범위) | [학습 JSON](gru_training_results.json) |
| 공통 Python 로직 리팩터링 | [코드 구조 안내의 이전 검증 기록](../guides/python_structure.md#이전-리팩터링-검증-기록) | [리팩터링 JSON](refactoring_results.json) |
| FastAPI·별도 워커 연결 | [서빙 안내](../guides/serving.md) | [서빙 JSON](serving_results.json) |
| 역할별 Python 패키지 정리 | [코드 구조 안내](../guides/python_structure.md) | [패키지 변경 JSON](package_layout_results.json) |
| Mock 학습·지표 계산·테스트 워커 추론 연결 | [GRU 가이드의 Mock 범위](../guides/gru_training.md) | [Mock 실행 JSON](mock_pipeline_results.json) |
| 독립 test 평가 CLI·CPU/MPS 추론 | [모델 성능 평가](../guides/evaluation.md) | [평가 실행 JSON](evaluation_results.json) |

실행 결과 JSON의 내용과 해시는 문서 이동을 이유로 갱신하지 않았습니다.
그 안의 코드 경로·실행 경로는 당시 위치일 수 있습니다. 현재 문서의 링크와 실행용 샘플 목록은
새 경로를 사용합니다. 초기 보고서의 PNG 저장 방식이나 crop 진단을 현재 추론 경로로 읽지 마세요.
