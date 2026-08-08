"""Content addressing, cache-key derivation, and the columnar gate."""

from pipeline.checksum import compute_pipeline_version, sha256_bytes, sha256_file
from pipeline.structure import classify_structure, is_in_scope


def test_checksum_is_content_based_not_filename_based(tmp_path):
    a = tmp_path / "resume.txt"
    b = tmp_path / "totally_different_name.bin"
    a.write_bytes(b"same bytes")
    b.write_bytes(b"same bytes")
    assert sha256_file(a) == sha256_file(b) == sha256_bytes(b"same bytes")


def test_pipeline_version_changes_on_prompt_change():
    v1 = compute_pipeline_version("presidio", [], "prompt A", "1")
    v2 = compute_pipeline_version("presidio", [], "prompt B", "1")
    v3 = compute_pipeline_version("presidio_genai", [], "prompt A", "1")
    assert v1 != v2 and v1 != v3


def test_pipeline_version_ignores_model_order():
    a = compute_pipeline_version("genai_only", ["m1", "m2"], "p", "1")
    b = compute_pipeline_version("genai_only", ["m2", "m1"], "p", "1")
    assert a == b


def test_csv_extension_is_columnar_and_out_of_scope(tmp_path):
    f = tmp_path / "export.csv"
    f.write_text("a,b,c\n1,2,3\n")
    cls = classify_structure(f)
    assert cls == "structured_columnar"
    assert not is_in_scope(cls)


def test_prose_txt_is_unstructured(tmp_path):
    f = tmp_path / "letter.txt"
    text = "Dear team,\n\nThis is a normal letter about quarterly planning.\n"
    f.write_text(text)
    assert classify_structure(f, sample_text=text) == "unstructured"


def test_delimited_content_in_txt_is_caught(tmp_path):
    f = tmp_path / "disguised.txt"
    text = "name,email,phone\nrow,row,row\nrow,row,row\nrow,row,row\n"
    f.write_text(text)
    assert classify_structure(f, sample_text=text) == "structured_columnar"


def test_pdf_is_semi_structured():
    assert classify_structure("report.pdf") == "semi_structured"
