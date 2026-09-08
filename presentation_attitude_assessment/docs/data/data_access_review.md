# 공개 영상 접근·이용 조건 검토

[문서 목차](../README.md)

> 2026-09-07 조사 시점의 기록입니다. 외부 접근 조건을 이번 문서 정리에서 재확인한 것은 아닙니다. 후속 영상 처리 범위는 [전체 영상 안내](../guides/whole_video_pipeline.md)를 참고합니다.

후속 상태: [MIT 700프레임 연속 검증](../history/mit_continuity_review.md)을 완료했다. 아래는 접근 확인 당시의 기록이다.

확인일: 2026-09-07. 공개 페이지 확인, 실제 파일 확보, 학습 적합성은 서로 구분한다.
계정 등록·접근 신청·약관 동의·미디어 재배포는 진행하지 않았다.

## 이번 단계 결과

**전체 원본 2개를 추가 확보했다.** 기존 짧은 클립과 같은 발표자·원본이므로
새로운 발표자 2명이 추가된 것은 아니다. 현재 총 7파일은 독립 원본 4개,
발표자 4명에 해당한다. 태도 라벨과 학습 가능 확정 파일은 여전히 0건이다.

| 새 파일 | 길이·영상 | 실제 확인 범위 | 배포 문서의 이용 조건 |
|---|---|---|---|
| [MIT 심리학 강연 원본](https://osf.io/download/pae7w/) `3Educator_id1_psych_vid1.mp4` | 49분 44초, 640×360, 약 29.97fps | 다운로드·해시·ffprobe, 874.86초의 원본 대조 프레임 1개 | CC BY-NC-SA 4.0 |
| [AOC 의회 발언 원본](https://osf.io/download/ybz85/) `1Politician_id1_AOC_vid1_speechCongress2019.mp4` | 4분 23초, 640×360, 약 23.98fps | 다운로드·해시·ffprobe, 41.37초의 원본 대조 프레임 1개 | 배포자가 Public Domain으로 명시 |

두 파일 모두 HTTP 200, OSF의 파일 크기·MD5 일치, SHA-256 기록, 프레임 디코딩을
확인했다. 전체 시청이나 새 원본의 MediaPipe 연속 검출 검사는 아직 하지 않았다.
의회 영상의 Public Domain 표기는 배포 문서의 주장으로 기록하며, 모든 의회 영상에
일반화하거나 독립적으로 권리 관계를 확인했다는 뜻으로 쓰지 않는다.

## 후보별 접근 상태

| 후보·공식 출처 | 현재 접근 결과 | 조건 확인 범위 | 우리 목표와의 차이·후속 판단 |
|---|---|---|---|
| [GESRes](https://osf.io/9zkfm/) | 공개 OSF에서 위 2개 원본 확보 | 파일별 PDF 2페이지와 배포 목록 대조. 아래 예외 존재 | 현장 청중을 상대하는 영상. 우선 추출 시험용이며 태도 정답은 별도로 필요 |
| [First Impressions V2](https://chalearnlap.cvc.uab.cat/dataset/24/description/) | 학습 파일 링크가 로그인 화면으로 이동 | 사이트 기본 조건은 별도 명시가 없으면 CC BY-NC 4.0. 로그인 뒤 아카이브 조건 미확인 | 카메라를 향해 말하는 10,000개, 평균 약 15초 클립. 손 가시성은 미확인이며 전체 발표 맥락이 짧음. 기존 성격·면접 라벨을 태도 라벨로 바꾸지 않음 |
| [MIT Interview](https://roc-hci.com/past-projects/automated-prediction-of-job-interview-performances/) | 학술 이메일을 이용한 신청 필요 | 공식 안내에 학술 이메일과 이용 조건 동의 요구. 전체 조건·실제 파일 미확보 | 69명, 138회 인터뷰. 카메라 대상 발표와 맥락이 다름 |
| [3MT_French](https://zenodo.org/records/7603511) | 공개 API의 `access_right`가 `restricted`, `files`는 빈 배열 | 비로그인 응답에 라이선스·접근 조건 필드 없음 | 프랑스어 현장 발표. 원본 접근 후 구도와 목표 라벨 적합성을 판단해야 함 |
| [POM](https://github.com/eusip/POM) | 등록 폼 접근 가능, 영상 미확보 | 이름·이메일·소속·용도와 연구용 사용 확인 요구. 검사한 폼에는 완전한 라이선스 본문 없음 | 의견 표현 영상. 얼굴·손 구도와 영상 전체 맥락 미검토 |
| [PATS](https://github.com/chahuja/pats) | 공식 README에서 특징·음성 다운로드와 원본 링크 방식 확인 | README에 CC BY-NC 2.0 명시. 원본 영상 링크별 가용성 미확인 | 처리된 pose/audio/text와 원본 URL 중심. 바로 MediaPipe에 넣을 원본 영상 묶음을 확보한 것은 아님 |

First Impressions V2가 카메라 대상이라는 점에서는 더 가까운 후보이나, 파일 접근과
손 가시성 확인이 남아 있다. GESRes를 최종 학습 데이터로 선정한 상태는 아니다.
공개 데이터셋이 없는 것이 아니라, **목표 라벨·구도·접근 조건까지 맞는 데이터는
아직 확보하지 못했다.**

## GESRes 파일별 권한 대조

[배포자의 Licensing_information.pdf](https://osf.io/download/qmx29/)를 전부 읽고
OSF의 전체 영상 목록과 `GESRes_dataset.csv`의 원본 ID를 대조했다.

- MIT 심리학 원본은 CC BY-NC-SA 4.0과 출처 표기가 명시되어 있다.
  [MIT OCW 공식 이용 조건](https://ocw.mit.edu/pages/privacy-and-terms-of-use/)도
  해당 라이선스와 출처·비상업·동일조건 배포 요건을 안내한다. 원본·편집본을 공개할 때
  라이선스와 변경 여부를 함께 표시해야 한다. 이 검토로 모델 가중치의 배포 조건까지 확정하지 않는다.
- Boebert 원본은 C-SPAN과 맺은 비독점 계약에 따라 해당 데이터셋의 비상업 학술 연구용
  수록을 허용했다는 설명이다. 이를 모든 후속 이용자의 재배포 허가로 확대하지 않는다.
- `2Clinician_id1_vid1`은 원저자·등장인물의 허가를 받았다고만 설명하며,
  일반 후속 이용자에게 적용되는 구체적인 라이선스는 확인되지 않았다.
- UVA 법학·Yale 정치 강연은 비상업 이용으로 설명하지만 PDF의 ID는 각각
  `3Educator_id1_law`, `3Educator_id1_Politics_vid1`이다. 실제 CSV·파일의
  `3Educator_id3_law`, `3Educator_id2_Politics_vid1`과 불일치한다.
  제목은 대응하는 것으로 보이지만 정확한 연결은 추가 확인 대상으로 남긴다.
- **`2Clinician_id3_vid1`은 PDF에서 재배포 권한이 없어 미포함이라고 설명하지만
  실제 공개 폴더에는 영상 파일이 있다.** 목록과 문서가 충돌하므로 다운로드·사용 후보에서 보류했다.

따라서 GESRes 전체 영상에 하나의 라이선스를 적용하지 않는다. 기존 Yale·UVA 샘플도
접근할 수 있다는 사실만으로 공개 재배포나 학습 적합성을 확정하지 않는다.

MIT 원본의 출처 표기 기준: MIT OpenCourseWare,
“Lec 1 | MIT 9.00SC Introduction to Psychology, Spring 2011”, CC BY-NC-SA 4.0.
이는 배포 PDF의 표기이며 [공식 강의 페이지](https://ocw.mit.edu/courses/9-00sc-introduction-to-psychology-fall-2011/resources/lecture-1-introduction/)의 학기명은 Fall 2011이다.

## 기록과 다음 단계

- [샘플 목록](sample_inventory.json): 7개 파일의 출처·해시·검토 범위·원본/발표자 ID.
  같은 원본의 짧은 클립과 전체 파일을 서로 다른 학습·평가 분할에 넣지 않는다.
- [접근 검토 기록](data_access_review.json): 후보별 상태, 새 다운로드 메타데이터,
  로컬 증거 파일의 해시. HTML·PDF·CSV와 미디어는 Git 제외 경로에만 보관한다.
- 로컬 증거 위치: 저장소 루트의 `.local-data/presentation-attitude/access-review/`.
  MIT Interview 안내는 웹 도구로 확인했지만 별도 urllib 저장 요청은 HTTP 406으로 실패했다.
  다운로드 성공으로 기록하지 않았다.

다음은 **확보한 MIT 심리학 강연의 연속 구간을 원본 그대로 MediaPipe에 넣고 얼굴·손
검출의 지속성을 확인하는 것**이다. 단일 대조 프레임이나 짧은 클립의 성공을 전체 강연의
성공으로 간주하지 않는다. 이후 전체 맥락 검토를 거쳐 태도 라벨 초안을 작성한다.
현재 사용자가 직접 촬영할 필요는 없다.

추가 접근 근거: [First Impressions 파일 접근](https://chalearnlap.cvc.uab.es/dataset/24/data/41/files/),
[ChaLearn 기본 이용 조건](https://chalearnlap.cvc.uab.cat/),
[3MT_French 공개 API](https://zenodo.org/api/records/7603511),
[POM 등록 폼](https://service.tsi.telecom-paristech.fr/cgi-bin/user-service/subscribe.cgi?form=&ident=POM&license=1).
