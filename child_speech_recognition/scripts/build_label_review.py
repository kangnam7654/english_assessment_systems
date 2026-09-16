"""Build an evidence queue; ASR disagreements are never automatic corrections."""

import hashlib
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / ".local-data/speechocean-audit"


def norm(text):
    return " ".join(re.sub(r"[^a-z0-9'\s]", " ", text.lower()).split())


def main():
    sample = json.loads((AUDIT / "review-sample.json").read_text())
    predictions = [
        json.loads(s)
        for s in (AUDIT / "whisper-predictions.jsonl").read_text().splitlines()
    ]
    by_id = {r["id"]: r for r in predictions}
    assert len(by_id) == len(predictions) == len(sample) == 105
    digit_words = [
        "ZERO",
        "ONE",
        "TWO",
        "THREE",
        "FOUR",
        "FIVE",
        "SIX",
        "SEVEN",
        "EIGHT",
        "NINE",
    ]
    records = []
    cards = []
    for row in sample:
        prediction = by_id[row["id"]]
        assert (
            prediction["audio_sha256"]
            == row["audio_sha256"]
            == hashlib.sha256((AUDIT / row["source_path"]).read_bytes()).hexdigest()
        )
        hypothesis = prediction["text"].strip()
        same = norm(row["text"]) == norm(hypothesis)
        digits = re.sub(r"[^0-9]", "", hypothesis)
        numeric = (
            bool(digits)
            and not re.search("[a-zA-Z]", hypothesis)
            and row["text"].split() == [digit_words[int(d)] for d in digits]
        )
        status = (
            "normalized_match"
            if same
            else "numeric_format_equivalence"
            if numeric
            else "needs_audio_adjudication"
        )
        record = {
            **row,
            "whisper": hypothesis,
            "status": status,
            "corrected_text": None,
            "audio_adjudicated": False,
        }
        records.append(record)
        words = ", ".join(
            f"{w['text']}={w['accuracy']}" for w in row["word_annotations"]
        )
        cards.append(
            f"<article><h2>{row['id']} · {row['split']} · {row['age']}세</h2><p>{status}</p><p>제공 문장: {html.escape(row['text'])}</p><p>Whisper: {html.escape(hypothesis)}</p><p>원본 단어 발음 점수: {html.escape(words)}</p><audio controls preload='none' src='{row['source_path']}'></audio></article>"
        )
    (AUDIT / "review-queue.json").write_text(json.dumps(records, indent=2) + "\n")
    (AUDIT / "index.html").write_text(
        "<!doctype html><html lang='ko'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>라벨 검수 후보</title><style>body{max-width:900px;margin:30px auto;padding:20px;font-family:system-ui}article{border-top:1px solid #ccc;padding:15px 0}audio{width:100%}h2{font-size:18px}</style><h1>라벨 검수 후보 105개</h1><p>직접 청취 판정 전의 자동 교차검증입니다. Whisper 출력은 정답이 아닙니다. 원본 라벨 변경 없음.</p>"
        + "\n".join(cards)
        + "<footer>speechocean762, Junbo Zhang et al. (2021). <a href='https://www.openslr.org/101/'>Source</a> · <a href='https://creativecommons.org/licenses/by/4.0/'>CC BY 4.0</a>. Audio and original annotations unchanged.</footer></html>"
    )
    summary = json.loads((AUDIT / "structural-summary.json").read_text())
    summary["whisper"] = {
        "model": predictions[0]["model"],
        "revision": predictions[0]["revision"],
        "reference_prompt": False,
        "count": len(records),
        "normalized_match": sum(r["status"] == "normalized_match" for r in records),
        "numeric_format_equivalence": sum(
            r["status"] == "numeric_format_equivalence" for r in records
        ),
        "needs_audio_adjudication": sum(
            r["status"] == "needs_audio_adjudication" for r in records
        ),
    }
    (ROOT / "child_speech_recognition/results/label-audit.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
