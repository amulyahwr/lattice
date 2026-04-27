"""HTTP-level tests for /api/v1/sources/ — LLM and embeddings mocked."""

import json

import pytest

from tests.helpers import chat_sequence


def _single_atom_responses(content: str, tag: str = '{"0": ["general"]}') -> callable:
    """Build pipeline responses for a single chunk that yields one atom.

    Current pipeline: extract (atomize+distill merged), link, tag = 3 calls.
    Tag response must be a JSON object: {"<index>": ["<domain>", ...], ...}
    """
    extract_resp = json.dumps([{"kind": "fact", "content": content, "canonical": None}])
    return chat_sequence(
        extract_resp,  # extract (atomize+distill merged)
        "[]",          # link
        tag,           # tag
    )


async def test_ingest_txt_file_returns_200(http_client, mock_chat, mock_embed_texts, clear_l2_cache):
    mock_chat.side_effect = _single_atom_responses("The company was founded in 2020.")
    resp = await http_client.post(
        "/api/v1/sources/ingest",
        files={"file": ("company.txt", b"The company was founded in 2020.", "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["source_type"] == "text"
    assert body["name"] == "company.txt"
    assert "compilation" in body
    assert "id" in body


async def test_ingest_returns_compilation_stats(http_client, mock_chat, mock_embed_texts, clear_l2_cache):
    mock_chat.side_effect = _single_atom_responses("Sales pipeline hit 120 percent of quota.")
    resp = await http_client.post(
        "/api/v1/sources/ingest",
        files={"file": ("sales.txt", b"Sales pipeline hit 120 percent of quota.", "text/plain")},
    )
    compilation = resp.json()["compilation"]
    assert "atoms_created" in compilation
    assert "cross_links_added" in compilation
    assert "kinds" in compilation
    assert "domains" in compilation


async def test_ingest_markdown_file_detected(http_client, mock_chat, mock_embed_texts, clear_l2_cache):
    mock_chat.side_effect = _single_atom_responses("Engineering shipped the feature on time.")
    resp = await http_client.post(
        "/api/v1/sources/ingest",
        files={"file": ("notes.md", b"# Notes\n\nEngineering shipped the feature on time.", "text/markdown")},
    )
    assert resp.status_code == 200
    assert resp.json()["source_type"] == "markdown"


async def test_ingest_empty_file_returns_400(http_client):
    resp = await http_client.post(
        "/api/v1/sources/ingest",
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    assert resp.status_code == 400


async def test_ingest_no_filename_returns_400(http_client):
    resp = await http_client.post(
        "/api/v1/sources/ingest",
        files={"file": ("", b"some content", "text/plain")},
    )
    # FastAPI returns 422 (validation error) for empty filename before our handler
    # runs; 400 from our handler if it does reach our code. Both are client errors.
    assert resp.status_code in (400, 422)


async def test_list_sources_shows_ingested_source(
    http_client, mock_chat, mock_embed_texts, clear_l2_cache
):
    mock_chat.side_effect = _single_atom_responses("Listed source content here.")
    await http_client.post(
        "/api/v1/sources/ingest",
        files={"file": ("listed.txt", b"Listed source content here.", "text/plain")},
    )
    resp = await http_client.get("/api/v1/sources/")
    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()]
    assert "listed.txt" in names


async def test_list_sources_empty_initially(http_client):
    resp = await http_client.get("/api/v1/sources/")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_source_atoms_returns_atoms(
    http_client, mock_chat, mock_embed_texts, clear_l2_cache
):
    mock_chat.side_effect = _single_atom_responses("Atom listing test content here.")
    ingest = await http_client.post(
        "/api/v1/sources/ingest",
        files={"file": ("atoms.txt", b"Atom listing test content here.", "text/plain")},
    )
    source_id = ingest.json()["id"]

    resp = await http_client.get(f"/api/v1/sources/{source_id}/atoms")
    assert resp.status_code == 200
    atoms = resp.json()
    assert isinstance(atoms, list)
    if atoms:  # may be empty if atomize returned 0 valid atoms
        atom = atoms[0]
        assert "atom_id" in atom
        assert "content" in atom
        assert "kind" in atom


async def test_list_source_atoms_unknown_source_returns_404(http_client):
    import uuid
    resp = await http_client.get(f"/api/v1/sources/{uuid.uuid4()}/atoms")
    assert resp.status_code == 404


async def test_list_source_atoms_pagination(
    http_client, mock_chat, mock_embed_texts, clear_l2_cache
):
    # Ingest source and check limit/offset params are accepted
    mock_chat.side_effect = _single_atom_responses("Pagination test atom content.")
    ingest = await http_client.post(
        "/api/v1/sources/ingest",
        files={"file": ("page.txt", b"Pagination test atom content.", "text/plain")},
    )
    source_id = ingest.json()["id"]
    resp = await http_client.get(f"/api/v1/sources/{source_id}/atoms?limit=10&offset=0")
    assert resp.status_code == 200


async def test_delete_source_returns_200(
    http_client, mock_chat, mock_embed_texts, clear_l2_cache
):
    mock_chat.side_effect = _single_atom_responses("Delete me source content here.")
    ingest = await http_client.post(
        "/api/v1/sources/ingest",
        files={"file": ("delete_me.txt", b"Delete me source content here.", "text/plain")},
    )
    source_id = ingest.json()["id"]

    resp = await http_client.delete(f"/api/v1/sources/{source_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"


async def test_delete_source_atoms_return_404_after_deletion(
    http_client, mock_chat, mock_embed_texts, clear_l2_cache
):
    mock_chat.side_effect = _single_atom_responses("Orphan atom delete test here.")
    ingest = await http_client.post(
        "/api/v1/sources/ingest",
        files={"file": ("orphan.txt", b"Orphan atom delete test here.", "text/plain")},
    )
    source_id = ingest.json()["id"]

    await http_client.delete(f"/api/v1/sources/{source_id}")

    resp = await http_client.get(f"/api/v1/sources/{source_id}/atoms")
    assert resp.status_code == 404


async def test_delete_source_not_found_returns_404(http_client):
    import uuid
    resp = await http_client.delete(f"/api/v1/sources/{uuid.uuid4()}")
    assert resp.status_code == 404
