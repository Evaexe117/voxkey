from __future__ import annotations

from pathlib import Path

from voxkey import hints, paths


def test_blank_lines_and_comments_are_dropped(tmp_path: Path) -> None:
    source = tmp_path / "terms"
    source.write_text("Whisper\n\n# a comment\nPipeWire\n")
    assert hints.read_hints_file(source) == ["Whisper", "PipeWire"]


def test_an_indented_comment_is_also_dropped(tmp_path: Path) -> None:
    # The dictate implementation tested the raw line, so an indented comment
    # was kept as a vocabulary term. Strip first, then decide.
    source = tmp_path / "terms"
    source.write_text("Whisper\n   # indented comment\n")
    assert hints.read_hints_file(source) == ["Whisper"]


def test_directory_merges_files_in_sorted_order(tmp_path: Path) -> None:
    (tmp_path / "b.hints").write_text("Beta\n")
    (tmp_path / "a.hints").write_text("Alpha\n")
    assert hints.read_hints_dir(tmp_path) == ["Alpha", "Beta"]


def test_missing_directory_yields_nothing(tmp_path: Path) -> None:
    assert hints.read_hints_dir(tmp_path / "absent") == []


def test_subdirectories_are_ignored(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()
    (tmp_path / "a.hints").write_text("Alpha\n")
    assert hints.read_hints_dir(tmp_path) == ["Alpha"]


def test_deduplication_is_case_insensitive_and_keeps_the_first_spelling() -> None:
    assert hints.deduplicate(["PipeWire", "pipewire", "Whisper"]) == [
        "PipeWire",
        "Whisper",
    ]


def test_prompt_shape_matches_the_dictate_format() -> None:
    assert hints.build_prompt(["Whisper", "PipeWire"]) == (
        "Technical terms: Whisper, PipeWire."
    )


def test_prompt_of_nothing_is_none() -> None:
    assert hints.build_prompt([]) is None


def test_global_and_project_hints_merge(xdg: Path, tmp_path: Path) -> None:  # noqa: ARG001
    paths.hints_dir().mkdir(parents=True)
    (paths.hints_dir() / "global.hints").write_text("Whisper\n")

    project = tmp_path / "project"
    (project / paths.PROJECT_HINTS_DIRNAME).mkdir(parents=True)
    (project / paths.PROJECT_HINTS_DIRNAME / "local.hints").write_text("Numpy\n")

    assert hints.load_hints(project) == "Technical terms: Whisper, Numpy."


def test_legacy_project_directory_is_still_read(xdg: Path, tmp_path: Path) -> None:  # noqa: ARG001
    project = tmp_path / "project"
    (project / paths.LEGACY_PROJECT_HINTS_DIRNAME).mkdir(parents=True)
    (project / paths.LEGACY_PROJECT_HINTS_DIRNAME / "l.hints").write_text("Legacy\n")
    assert hints.load_hints(project) == "Technical terms: Legacy."


def test_no_hints_anywhere_yields_none(xdg: Path, tmp_path: Path) -> None:  # noqa: ARG001
    assert hints.load_hints(tmp_path / "empty") is None
