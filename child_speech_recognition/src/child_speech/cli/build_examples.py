"""Command-line entry point for child_speech.reporting.build_examples."""


def main() -> None:
    # Load ML dependencies only when this command is invoked.
    """Build verified private listening examples and public comparison summaries."""
    from child_speech.reporting.build_examples import main as run

    run()


if __name__ == "__main__":
    main()
