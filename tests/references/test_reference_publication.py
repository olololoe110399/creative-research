from __future__ import annotations

import pandas as pd
import pytest

from creative_research.references import pack as reference_pack
from creative_research.workspaces import references as reference_workspace


@pytest.mark.parametrize("identifier", ["../outside", "..", "a/b", "a\\b", ""])
def test_reference_identifiers_are_confined_before_writes(tmp_path, identifier):
    references = pd.DataFrame([{"reference_id": identifier, "source_media_path": "missing"}])
    output = tmp_path / "output"
    with pytest.raises(ValueError):
        reference_pack.copy_reference_media(references, output, root=tmp_path)
    with pytest.raises(ValueError):
        reference_workspace.write_reference_workspace(
            references,
            pd.DataFrame([{}]),
            system_population=pd.DataFrame(),
            system_map={},
            out_dir=output,
            media_mode="none",
        )
    assert not output.exists()


def test_media_copy_failure_retains_existing_complete_directory(tmp_path, monkeypatch):
    output = tmp_path / "output"
    media = output / "media"
    media.mkdir(parents=True)
    (media / "original.txt").write_text("old")
    source = tmp_path / "source"
    source.mkdir()
    references = pd.DataFrame([{"reference_id": "REF-0001", "source_media_path": str(source)}])

    def fail_copy(source, destination):
        destination.mkdir()
        (destination / "partial.txt").write_text("partial")
        raise OSError("copy failed")

    monkeypatch.setattr(reference_pack.shutil, "copytree", fail_copy)
    with pytest.raises(OSError, match="copy failed"):
        reference_pack.copy_reference_media(references, output, root=tmp_path)
    assert (media / "original.txt").read_text() == "old"
    assert list(output.iterdir()) == [media]


def test_jsonl_export_failure_retains_previous_table(tmp_path, monkeypatch):
    target = tmp_path / "references.jsonl"
    target.write_text('{"complete": true}\n')

    def fail_write(frame, path, **kwargs):
        path.write_text('{"partial":')
        raise OSError("serialization failed")

    monkeypatch.setattr(pd.DataFrame, "to_json", fail_write)
    with pytest.raises(OSError, match="serialization failed"):
        reference_pack.write_table(pd.DataFrame([{"new": True}]), target)

    assert target.read_text() == '{"complete": true}\n'
    assert list(tmp_path.iterdir()) == [target]
