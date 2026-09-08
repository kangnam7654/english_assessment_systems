# English Assessment Systems

[한국어](README.ko.md)

**Assessment workflows, from presentation video to English writing.**

A portfolio monorepo rebuilding work from Creverse. Each project can be explored
independently and shares one Python environment. Company code, private datasets
and trained weights are not included.

## Projects

### [Presentation Attitude Assessment →](presentation_attitude_assessment/README.md)

Extract face and hand movement from video, prepare landmark sequences, and train
a small classifier. Includes evaluation and a local upload API with an analysis worker.

**MediaPipe · FFmpeg · PyTorch · FastAPI**

The pipeline is implemented. A validated attitude classifier still requires real labeled data.

### [English Writing Data Synthesis →](writing_data_synthesis/README.md)

Generate essays for a target grade and proficiency level, then assess them against
a rubric through a LangGraph workflow. Includes an API and a Next.js demo.

**LangGraph · Ollama · FastAPI · Next.js**

Outputs are candidate synthetic examples; human review and batch dataset export remain future work.

## Get started

From the repository root:

```sh
uv sync --locked
```

Both projects use **Python 3.13** and the root `uv.lock`.
Open a project above for its run commands.

[Python setup and dependencies](docs/python_environment.md) ·
[MIT License](LICENSE)

Third-party media retain their original terms.
