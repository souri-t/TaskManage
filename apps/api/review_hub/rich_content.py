from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from xml.etree import ElementTree

import httpx
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import DiagramRenderCache, Finding, FindingArtifact, FindingArtifactReference, FindingContentVersion

ATTACHMENT_RE = re.compile(r"attachment://(ART-\d{6,})")
FENCE_RE = re.compile(r"```(mermaid|plantuml)\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
BLOCKED_PLANTUML = re.compile(r"^\s*!(?:include|includeurl|import)\b|https?://|file:", re.IGNORECASE | re.MULTILINE)
IMAGE_TYPES = {"image/png": b"\x89PNG\r\n\x1a\n", "image/jpeg": b"\xff\xd8\xff", "image/webp": b"RIFF"}


def sha256(value: bytes | str) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def artifact_display_id(value: str) -> int:
    return int(value.removeprefix("ART-"))


def validate_image(data: bytes, mime_type: str) -> None:
    settings = get_settings()
    if not data or len(data) > settings.artifact_max_bytes or mime_type not in IMAGE_TYPES:
        raise HTTPException(status_code=422, detail="許可されていない画像形式またはサイズです")
    valid = data.startswith(IMAGE_TYPES[mime_type])
    if mime_type == "image/webp":
        valid = valid and len(data) >= 12 and data[8:12] == b"WEBP"
    if not valid:
        raise HTTPException(status_code=422, detail="MIME typeと画像形式が一致しません")


def next_artifact_sequence(session: Session) -> int:
    return int(session.scalar(select(func.max(FindingArtifact.sequence))) or 0) + 1


def content_version(session: Session, finding: Finding) -> FindingContentVersion:
    version = session.scalar(select(FindingContentVersion).where(FindingContentVersion.finding_id == finding.id).order_by(FindingContentVersion.version.desc()))
    if version is None:
        version = FindingContentVersion(finding_id=finding.id, version=1, content_markdown=finding.description_markdown, content_sha256=sha256(finding.description_markdown), created_by=finding.created_by)
        session.add(version)
        session.flush()
    return version


def add_content_version(session: Session, finding: Finding, markdown: str, actor: str) -> FindingContentVersion:
    current = content_version(session, finding)
    version = FindingContentVersion(finding_id=finding.id, version=current.version + 1, content_markdown=markdown, content_sha256=sha256(markdown), created_by=actor)
    session.add(version)
    session.flush()
    references = sorted(set(ATTACHMENT_RE.findall(markdown)))
    for display_id in references:
        artifact = session.scalar(select(FindingArtifact).where(FindingArtifact.sequence == artifact_display_id(display_id), FindingArtifact.finding_id == finding.id))
        if artifact is None or artifact.deleted_at is not None:
            raise HTTPException(status_code=422, detail=f"添付物を参照できません: {display_id}")
        session.add(FindingArtifactReference(content_version_id=version.id, artifact_id=artifact.id))
    return version


def sanitize_svg(svg: bytes) -> bytes:
    try:
        root = ElementTree.fromstring(svg)
    except ElementTree.ParseError as exc:
        raise HTTPException(status_code=422, detail="描画結果が有効なSVGではありません") from exc
    for node in list(root.iter()):
        for key in list(node.attrib):
            value = node.attrib[key]
            if key.lower().startswith("on") or key.lower() in {"href", "xlink:href"} or "javascript:" in value.lower() or value.lower().startswith(("http:", "https:", "file:")):
                del node.attrib[key]
        for child in list(node):
            if child.tag.split("}")[-1].lower() in {"script", "foreignobject", "iframe", "object", "embed"}:
                node.remove(child)
    ElementTree.register_namespace("", "http://www.w3.org/2000/svg")
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)


def validate_diagram(engine: str, source: str) -> None:
    settings = get_settings()
    if len(source.encode()) > settings.diagram_source_max_bytes:
        raise HTTPException(status_code=422, detail="図のソースが大きすぎます")
    if engine == "plantuml" and BLOCKED_PLANTUML.search(source):
        raise HTTPException(status_code=422, detail="PlantUMLの外部参照記法は使用できません")


def render_diagram(session: Session, engine: str, source: str, cache: bool = True) -> DiagramRenderCache | bytes:
    validate_diagram(engine, source)
    digest = sha256(source)
    cached = session.scalar(select(DiagramRenderCache).where(DiagramRenderCache.engine == engine, DiagramRenderCache.source_sha256 == digest, DiagramRenderCache.output_format == "svg"))
    if cached and b"xmlns=" in cached.svg[:300]:
        return cached
    if cached:
        session.delete(cached)
        session.flush()
    settings = get_settings()
    if engine == "mermaid":
        url, data, headers = f"{settings.kroki_url}/mermaid/svg", source.encode(), {"Content-Type": "text/plain; charset=utf-8"}
    else:
        url, data, headers = f"{settings.plantuml_url}/svg", source.encode(), {"Content-Type": "text/plain; charset=utf-8"}
    try:
        with httpx.Client(timeout=settings.diagram_timeout_seconds, follow_redirects=True) as client:
            response = client.post(url, content=data, headers=headers)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=422, detail="図の描画に失敗しました") from exc
    svg = sanitize_svg(response.content)
    if not cache:
        return svg
    item = DiagramRenderCache(engine=engine, source_sha256=digest, output_format="svg", svg=svg)
    session.add(item)
    session.flush()
    return item


def validate_markdown(session: Session, finding: Finding, markdown: str) -> dict:
    for artifact_id in set(ATTACHMENT_RE.findall(markdown)):
        artifact = session.scalar(select(FindingArtifact).where(FindingArtifact.sequence == artifact_display_id(artifact_id), FindingArtifact.finding_id == finding.id))
        if artifact is None or artifact.deleted_at is not None:
            raise HTTPException(status_code=422, detail=f"添付物を参照できません: {artifact_id}")
    diagrams = []
    for engine, source in FENCE_RE.findall(markdown):
        render_diagram(session, engine.lower(), source, cache=False)
        diagrams.append(engine.lower())
    return {"attachments": sorted(set(ATTACHMENT_RE.findall(markdown))), "diagrams": diagrams, "validated_at": datetime.now(timezone.utc)}
