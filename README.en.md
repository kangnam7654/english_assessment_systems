# English Assessment Systems

[한국어](README.md) · [Projects](#projects) · [Quick Start](#quick-start) · [Repository layout](docs/repository_structure.md)

## About

**Presentation-video analysis, English writing data generation and child English ASR in one repository.**

This portfolio monorepo reconstructs three areas of work at Creverse.
Each project can be explored independently. The presentation and writing modules share
Python 3.13 and `uv.lock`; child ASR training uses a separate CUDA environment.
Company code, internal data and trained weights are not included.

## Projects

### [Presentation Attitude Assessment →](presentation_attitude_assessment/README.en.md)

**A whole-video attitude assessment pipeline using face and hand landmarks.**
FFmpeg reads video frames; MediaPipe coordinates are normalized and smoothed before
they reach a PyTorch GRU. Explore the preprocessing visuals, synthetic training and
evaluation examples, and a FastAPI upload demo.

`FFmpeg` · `MediaPipe` · `PyTorch` · `FastAPI`

### [Writing Data Synthesis →](writing_data_synthesis/README.en.md)

**Generate and assess English writing against criteria for a requested grade and genre.**
The workflow selects one of 39 rubric combinations across kindergarten through grade 12,
then connects generation, assessment and result storage in Python.
A Mock API and UI run without a model server.

`Python` · `OpenAI-compatible SDK` · `FastAPI` · `SQLite`

### [Child Speech Recognition →](child_speech_recognition/README.en.md)

**Fine-tune Parakeet for Korean children's English speech.**
WER on the fixed AI Hub Test split decreased from **14.45% to 8.50%**.
Public metrics and transcript examples are available; source audio and reference files
are not redistributed.

`NVIDIA NeMo` · `Parakeet TDT` · `PyTorch` · `AI Hub`

## Quick Start

Install [uv](https://docs.astral.sh/uv/) and prepare the shared environment from the repository root:

```sh
uv sync --locked
```

Choose a runnable example:

| Project | Start here | What you can inspect |
|---|---|---|
| Presentation attitude | [Quick Start](presentation_attitude_assessment/README.en.md#quick-start) | Training and evaluation with synthetic coordinates |
| Writing data | [Quick Start](writing_data_synthesis/README.en.md#quick-start) | Mock generation, assessment and SQLite storage |
| Child ASR | [Result and instructions](child_speech_recognition/README.en.md#quick-start) | Public fixed-Test metrics |

For CUDA training or workflows needing source data, follow the corresponding project guide.
[Shared Python environment](docs/python_environment.md) · [Repository layout](docs/repository_structure.md)

## Repository Layout

| Path | Contents |
|---|---|
| `presentation_attitude_assessment/` | Video preprocessing, training and upload API |
| `writing_data_synthesis/` | Grade rubrics, generation and assessment |
| `child_speech_recognition/` | Child ASR experiments and public results |
| `docs/` | Shared environment and folder conventions |

[MIT License](LICENSE). Third-party data and media retain their original terms.
