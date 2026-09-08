# MIT 강연 연속 랜드마크 검증

[문서 목차](../README.md)

> 과거 실험 기록입니다. 본문의 환경·테스트 수·다음 작업은 당시 기준이며, 현재 사용법은 문서 목차를 따릅니다.

후속 구현: [FFmpeg → NumPy 스트리밍](../guides/ffmpeg_streaming.md)으로 입력 경로를 바꿨다.
아래는 변경 전 PNG 경로의 검증 기록이다. 현재 코드로 아래 비교 영상까지 재현하려면
audit 명령에 `--save-frames`를 추가한다.

검증일: 2026-09-07. **추출·전처리는 실행됐고 연속 좌표도 확보했으나,
이 강연 전체를 목표 태도 학습 자료로 채택하는 것은 보류한다.**
슬라이드 편집, 검출 누락과 오검출이 함께 확인됐다. 태도 라벨은 부여하지 않았다.

## 영상 처리 방식

이 검증 당시 `audit_landmarks.py`는 `subprocess.run([...], check=True)`으로 FFmpeg를 실행한다.
FFmpeg가 원본을 디코딩하고 `fps=fps=5:start_time=0`으로 샘플링해 PNG를 저장한다.
Python은 그 PNG를 순서대로 읽어 RGB로 변환하고 MediaPipe VIDEO 모드에 넣는다.
OpenCV는 이미지 읽기·색 변환·검증 이미지 그리기에 사용한다. `VideoCapture`는 쓰지 않는다.
얼굴 crop, YuNet, 프레임 확대와 검출 임계값 변경도 이번 검증에는 없다.

사용자는 과거 FFmpeg 기반 Python 순회 클래스를 사용했던 것으로 기억하지만 정확한
라이브러리는 미확인이다. [Python subprocess](https://docs.python.org/3/library/subprocess.html)의
`Popen`과 [FFmpeg pipe 출력](https://ffmpeg.org/ffmpeg-protocols.html#pipe)을 연결해
프레임을 순회하는 클래스는 가능한 구현이다. 검증 당시 재구현은 검사할 PNG를 남기는 방식이었으며,
당시에는 파이프 iterator 클래스나 외부 FFmpeg Python 래퍼를 사용하지 않았다.
OpenCV 영상 순회와의 속도 우위는 측정하지 않았다.

## 범위와 결과

원본은 `3Educator_id1_psych_vid1.mp4`이다. 길이의 5·20·40·60·80·95%를 중심으로
20초씩 6구간을 고정 선택했다. 기존 제스처 클립의 원본 시점 주변 20초는 별도 확인 구간이다.
각각 5fps × 20초 = 100프레임, 총 700프레임이다. 이전 제스처를 아는 상태에서 고른
추가 구간을 무작위 표본으로 취급하지 않는다. 전체 약 50분에 대한 검출률 추정도 아니다.

| 구간 (원본 초, 끝 제외) | 얼굴 검출 | 손 1개 이상 | 얼굴+손 1개 이상 | 얼굴 최장 연속 | 얼굴+손 최장 연속 |
|---|---:|---:|---:|---:|---:|
| 139–159 | 48/100 | 1/100 | 0/100 | 36프레임 | 0 |
| 587–607 | 2/100 | 0/100 | 0/100 | 1프레임 | 0 |
| 1184–1204 | 99/100 | 0/100 | 0/100 | 85프레임 | 0 |
| 1780–1800 | 81/100 | 79/100 | 73/100 | 78프레임 | 60프레임 |
| 2377–2397 | 92/100 | 0/100 | 0/100 | 48프레임 | 0 |
| 2825–2845 | 26/100 | 26/100 | 26/100 | 26프레임 | 26프레임 |
| 865–885 (기존 제스처 주변) | 81/100 | 90/100 | 72/100 | 27프레임 | 12프레임 |

**이 표는 검출기의 출력이며 실제 사람이 보인 비율이나 정확도가 아니다.**
5fps에서 60프레임은 샘플 구간 길이로 12초, 첫·마지막 샘플의 시각 차이로는 11.8초다.
손 1개 이상이 연속 검출됐다는 것도 동일한 손의 ID가 유지됐다는 뜻은 아니다.
전처리의 좌우 슬롯에서는 1780–1800초 구간의 최장 유효 연속 길이가
Left 15프레임, Right 35프레임이었다. 검출 누락과 슬롯 검증 때문에 더 짧아진다.

## 원본과 대조한 문제

7개 구간의 contact sheet 전체와 전처리 비교 sheet 5개, 총 비교 프레임 15개를 확인했다.
700프레임 전체를 사람이 판독하거나 전체 영상을 연속 재생한 것은 아니다.

- **도형을 얼굴로 오검출:** 588.2초와 588.6초의 슬라이드 도형에 얼굴 좌표가 붙었다.
  587–607초 구간의 얼굴 검출 2건이 이 사례다. 현재 정규화도 이 출력을 받아들이므로
  `valid=true`는 실제 얼굴이라는 보증이 아니다. 오검출을 자동 제거하는 기능은 미구현이다.
- **얼굴을 손으로 오검출:** 140.0초 프레임에서 손 랜드마크가 얼굴 부위에 붙었다.
  이 프레임은 얼굴 기준점이 없어 손 특징으로 사용되지 않았지만, 원시 검출 수에는 포함된다.
- **얼굴이 있어도 누락:** 1186.8초, 2380.6초 등의 고개를 숙인 프레임에서 실제 얼굴은
  보이지만 검출되지 않았다. 867.2초에도 얼굴·손이 보이는 표본에서 검출 누락이 있다.
- **영상 편집에 의한 부재:** 153.8초, 1799.8초, 2825초 등은 슬라이드 화면이다.
  발표자가 자발적으로 카메라 밖으로 나간 것으로 판정할 수 없다.
- **손이 화면 아래 또는 가림:** 손이 보이지 않는 표본과 손이 보이는데 검출되지 않은
  표본이 모두 있다. 1780초에는 종이를 잡은 손이 보이지만 두 손 모두 미검출이다.

따라서 얼굴 검출률 50%를 그대로 사용자 기준의 얼굴 노출 50%에 대응시키지 않는다.
슬라이드 구간을 조용히 분모에서 빼거나, 선택한 20초 구간을 전체 발표의 정답으로 바꾸지도 않는다.

## 정규화·이동평균

얼굴 기준 XY 정규화와 연속 3프레임 중앙 이동평균을 기존 설정 그대로 적용했다.
원시 700개 레코드가 모두 그대로 남았고, 결측 좌표를 평균으로 채우지 않았다.
정규화 후 역변환의 최대 좌표 오차는 `1.1102230246251565e-16`이었다.
이는 수식의 가역성 검증이며 실제 촬영 거리 변화에 대한 정확도 검증은 아니다.
기존 평행이동·동일 비율 확대/축소 불변성 테스트도 통과했다.

1780–1800초 구간의 연속 3점 차분 RMS(얼굴 크기 단위)는 다음과 같다.

| 특징 | 정규화만 | 이동평균 후 |
|---|---:|---:|
| 얼굴 | 0.04797 | 0.02367 |
| Left | 0.10110 | 0.02821 |
| Right | 0.24011 | 0.08276 |

좌표의 급격한 변화는 감소했다. 다만 실제 빠른 제스처와 검출 떨림을 분리한 정답이 없으므로
이를 정확도 향상이나 노이즈만 제거했다는 증거로 쓰지 않는다. 1784.2–1785.2초,
2841.8–2842.2초, 874.6–875.0초의 비교 프레임에서는 전체 손 위치 변화가 남지만
개별 손가락 좌표가 실제 윤곽에서 벗어나는 사례도 있다. 모든 제스처의 보존은 미검증이다.
슬라이드·카메라 편집을 자동 탐지하는 장면 경계 처리도 현재 없다.

## 재현과 산출물

저장소 루트에서 실행한다. 출력 디렉터리는 새 경로여야 한다.

```sh
uv run --project presentation_attitude_assessment --locked presentation-audit --save-frames --plan presentation_attitude_assessment/configs/mit_audit_intervals.json --output .local-data/presentation-attitude/mit-audit-5fps
uv run --project presentation_attitude_assessment --locked presentation-preprocess --audit .local-data/presentation-attitude/mit-audit-5fps --output .local-data/presentation-attitude/mit-preprocess-5fps
uv run --project presentation_attitude_assessment --locked presentation-continuity --audit .local-data/presentation-attitude/mit-audit-5fps --processed .local-data/presentation-attitude/mit-preprocess-5fps --output .local-data/presentation-attitude/mit-continuity.json
uv run --project presentation_attitude_assessment --locked presentation-render --audit .local-data/presentation-attitude/mit-audit-5fps --processed .local-data/presentation-attitude/mit-preprocess-5fps --output .local-data/presentation-attitude/mit-preprocess-visuals
```

- [구간 계획](../../configs/mit_audit_intervals.json), [추출 결과](mit_audit_results.json),
  [전처리 결과](mit_preprocessing_results.json), [연속성 결과](mit_continuity_results.json).
- 실행 환경: Apple M4, 고정된 MediaPipe 0.10.32. CPU delegate 요청과 GL/Metal 초기화 로그가
  함께 존재한다. RTX 5090 실행이나 처리 속도 비교는 하지 않았다.
- 테스트 17개 통과. 원시 데이터 700개 보존·좌표 역변환·결측 유지 확인.
  비교 MP4 7개 모두 ffprobe로 1280×420, 5fps, 100프레임을 확인했다.
- 미디어·좌표 원본·비교 영상은 `.local-data/presentation-attitude/` 아래에만 보관한다.
  원본 출처와 이용 조건은 [접근 검토](../data/data_access_review.md)를 따른다.

다음 행동은 확보한 **의회 발언 원본에도 동일한 연속 검출 검사를 적용**하는 것이다.
MIT 강연은 오검출·누락·전처리 회귀 시험 자료로 남긴다. 목표인 카메라 대상 전체 발표
학습 데이터의 적합성은 별도 문제이며, 현재 학습 가능 파일과 태도 라벨은 모두 0건이다.
