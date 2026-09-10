from __future__ import annotations

import hashlib
import json
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .config import DEFAULT_TIMEOUT, USER_AGENT, source_config


@dataclass
class ProbeResult:
    source_id: str
    provider: str
    name: str
    category: str
    priority: str
    kind: str
    audit_status: str
    runtime_policy: str
    legal_gate: str
    technical_status: str
    http_status: Optional[int]
    latency_ms: Optional[int]
    content_type: Optional[str]
    service_name: Optional[str]
    resource_count: Optional[int]
    sample_resource: Optional[str]
    feature_count: Optional[int]
    schema_hash: Optional[str]
    discovered_links: List[str]
    error_type: Optional[str]
    error: Optional[str]
    checked_at: str

    def to_dict(self):
        return asdict(self)


def now_text() -> str:
    try:
        import pandas as pd
        return pd.Timestamp.now(tz="America/Santiago").isoformat()
    except Exception:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


def request_get(url, params=None, timeout=DEFAULT_TIMEOUT, stream=False):
    effective_timeout = min(timeout, source_config("mop")["timeout"]) if "rest-sit.mop.gob.cl" in url else timeout
    attempts = 1
    last_error = None

    for attempt in range(attempts):
        start = time.perf_counter()
        try:
            r = requests.get(
                url,
                params=params,
                timeout=effective_timeout,
                stream=stream,
                allow_redirects=True,
                headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            )
            elapsed = int((time.perf_counter() - start) * 1000)
            return r, elapsed
        except requests.exceptions.SSLError:
            raise
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(0.8 * (attempt + 1))
                continue
            raise

    raise last_error



def classify_error(exc) -> str:
    if isinstance(exc, requests.exceptions.SSLError):
        return "TLS_SSL"
    if isinstance(exc, requests.exceptions.Timeout):
        return "TIMEOUT"
    if isinstance(exc, requests.exceptions.ConnectionError):
        return "CONNECTION"
    if isinstance(exc, requests.exceptions.HTTPError):
        code = getattr(getattr(exc, "response", None), "status_code", None)
        return f"HTTP_{code}" if code else "HTTP_ERROR"
    text = str(exc)
    if "ArcGIS error" in text and "404" in text:
        return "ENDPOINT_404"
    if "ArcGIS error" in text:
        return "ARCGIS_ERROR"
    return "OTHER"

def base_result(source, **kwargs):
    payload = dict(
        source_id=source["id"],
        provider=source["provider"],
        name=source["name"],
        category=source["category"],
        priority=source["priority"],
        kind=source["kind"],
        audit_status=source["audit_status"],
        runtime_policy=source["runtime_policy"],
        legal_gate=source["legal_gate"],
        technical_status="SOURCE_ERROR",
        http_status=None,
        latency_ms=None,
        content_type=None,
        service_name=None,
        resource_count=None,
        sample_resource=None,
        feature_count=None,
        schema_hash=None,
        discovered_links=[],
        error_type=None,
        error=None,
        checked_at=now_text(),
    )
    payload.update(kwargs)
    return ProbeResult(**payload)


def stable_hash(obj) -> str:
    raw = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:20]


def arcgis_schema(meta):
    fields = meta.get("fields")
    if not isinstance(fields, list):
        return None
    payload = {
        "geometryType": meta.get("geometryType"),
        "objectIdField": meta.get("objectIdField"),
        "fields": [
            {
                "name": f.get("name"),
                "type": f.get("type"),
                "length": f.get("length"),
            } for f in fields
        ]
    }
    return stable_hash(payload)


def arcgis_json(url, timeout):
    r, latency = request_get(url, {"f": "json"}, timeout)
    http = r.status_code
    ctype = r.headers.get("content-type", "")
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(f"ArcGIS error: {data['error']}")
    return data, latency, http, ctype


def arcgis_count(layer_url, timeout):
    r, latency = request_get(
        layer_url.rstrip("/") + "/query",
        {
            "where": "1=1",
            "returnCountOnly": "true",
            "f": "json",
        },
        timeout,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("error"):
        raise RuntimeError(f"ArcGIS query error: {data['error']}")
    return data.get("count"), latency


def probe_arcgis(source, timeout):
    try:
        meta, latency, http, ctype = arcgis_json(source["url"], timeout)

        if source["kind"] == "arcgis_layer":
            fingerprint = arcgis_schema(meta)
            try:
                count, qlat = arcgis_count(source["url"], timeout)
                latency += qlat
                status = "OK"
                error = None
            except Exception as exc:
                count = None
                status = "DEGRADED"
                error = f"Metadata OK; query mínima falló: {exc}"

            return base_result(
                source,
                technical_status=status,
                http_status=http,
                latency_ms=latency,
                content_type=ctype,
                service_name=meta.get("name") or meta.get("mapName"),
                resource_count=1,
                sample_resource=meta.get("name"),
                feature_count=count,
                schema_hash=fingerprint,
                error=error,
            )

        layers = meta.get("layers") or []
        errors = []
        selected = None
        selected_meta = None
        selected_count = None

        for layer in layers[:15]:
            layer_id = layer.get("id")
            if layer_id is None:
                continue
            layer_url = source["url"].rstrip("/") + "/" + str(layer_id)
            try:
                lm, llat, _, _ = arcgis_json(layer_url, timeout)
                cnt, qlat = arcgis_count(layer_url, timeout)
                latency += llat + qlat
                selected = layer_url
                selected_meta = lm
                selected_count = cnt
                break
            except Exception as exc:
                errors.append(f"{layer_id}: {exc}")

        if selected_meta is not None:
            return base_result(
                source,
                technical_status="OK",
                http_status=http,
                latency_ms=latency,
                content_type=ctype,
                service_name=meta.get("mapName") or meta.get("name") or meta.get("serviceDescription"),
                resource_count=len(layers),
                sample_resource=selected_meta.get("name") or selected,
                feature_count=selected_count,
                schema_hash=arcgis_schema(selected_meta),
                discovered_links=[selected],
            )

        return base_result(
            source,
            technical_status="DEGRADED",
            http_status=http,
            latency_ms=latency,
            content_type=ctype,
            service_name=meta.get("mapName") or meta.get("name"),
            resource_count=len(layers),
            error=(
                "Servicio ArcGIS respondió pero no se logró una query canaria. "
                + (" | ".join(errors[:3]) if errors else "No se encontraron capas.")
            ),
        )
    except Exception as exc:
        return base_result(source, error_type=classify_error(exc), error=str(exc))


def strip_ns(tag):
    return tag.split("}", 1)[-1] if "}" in tag else tag


def parse_xml_names(root, parent_local, name_local):
    names = []
    for elem in root.iter():
        if strip_ns(elem.tag) != parent_local:
            continue
        for child in elem.iter():
            if strip_ns(child.tag) == name_local and child.text:
                text = child.text.strip()
                if text and text not in names:
                    names.append(text)
    return names


def xml_service_title(root):
    for elem in root.iter():
        if strip_ns(elem.tag) in ("Title", "ServiceType"):
            if elem.text and elem.text.strip():
                return elem.text.strip()
    return None


def probe_wms(source, timeout):
    try:
        r, latency = request_get(
            source["url"],
            {"service": "WMS", "request": "GetCapabilities"},
            timeout,
        )
        http = r.status_code
        ctype = r.headers.get("content-type", "")
        r.raise_for_status()

        root = ET.fromstring(r.content)
        layer_names = parse_xml_names(root, "Layer", "Name")
        fingerprint = stable_hash(layer_names) if layer_names else None

        return base_result(
            source,
            technical_status="OK" if layer_names else "DEGRADED",
            http_status=http,
            latency_ms=latency,
            content_type=ctype,
            service_name=xml_service_title(root),
            resource_count=len(layer_names),
            sample_resource=layer_names[0] if layer_names else None,
            schema_hash=fingerprint,
            error=None if layer_names else "GetCapabilities respondió pero no se detectaron Layer/Name.",
        )
    except Exception as exc:
        return base_result(source, error_type=classify_error(exc), error=str(exc))


def probe_wfs(source, timeout):
    try:
        r, latency = request_get(
            source["url"],
            {"service": "WFS", "request": "GetCapabilities"},
            timeout,
        )
        http = r.status_code
        ctype = r.headers.get("content-type", "")
        r.raise_for_status()
        root = ET.fromstring(r.content)

        feature_types = parse_xml_names(root, "FeatureType", "Name")
        fingerprint = stable_hash(feature_types) if feature_types else None
        hit_count = None
        hit_error = None

        if feature_types:
            typename = feature_types[0]
            attempts = [
                {
                    "service": "WFS", "version": "2.0.0", "request": "GetFeature",
                    "typeNames": typename, "resultType": "hits",
                },
                {
                    "service": "WFS", "version": "1.1.0", "request": "GetFeature",
                    "typeName": typename, "resultType": "hits",
                },
            ]
            for params in attempts:
                try:
                    rr, l2 = request_get(source["url"], params, timeout)
                    latency += l2
                    rr.raise_for_status()
                    txt = rr.text
                    m = re.search(r'numberMatched=["\'](\d+)["\']', txt)
                    if not m:
                        m = re.search(r'numberOfFeatures=["\'](\d+)["\']', txt)
                    if m:
                        hit_count = int(m.group(1))
                        break
                except Exception as exc:
                    hit_error = str(exc)

        status = "OK" if feature_types else "DEGRADED"
        return base_result(
            source,
            technical_status=status,
            http_status=http,
            latency_ms=latency,
            content_type=ctype,
            service_name=xml_service_title(root),
            resource_count=len(feature_types),
            sample_resource=feature_types[0] if feature_types else None,
            feature_count=hit_count,
            schema_hash=fingerprint,
            error=None if feature_types else "GetCapabilities respondió pero no se detectaron FeatureType/Name.",
        )
    except Exception as exc:
        return base_result(source, error_type=classify_error(exc), error=str(exc))


def probe_ckan(source, timeout):
    try:
        r, latency = request_get(source["url"], source.get("params"), timeout)
        http = r.status_code
        ctype = r.headers.get("content-type", "")
        r.raise_for_status()
        data = r.json()

        if not data.get("success"):
            raise RuntimeError("CKAN respondió success=false")

        result = data.get("result") or {}
        resources = result.get("resources") or []
        links = [x.get("url") for x in resources if x.get("url")][:50]
        names = [x.get("name") or x.get("format") for x in resources]

        return base_result(
            source,
            technical_status="OK",
            http_status=http,
            latency_ms=latency,
            content_type=ctype,
            service_name=result.get("title"),
            resource_count=len(resources),
            sample_resource=names[0] if names else None,
            discovered_links=links,
            schema_hash=stable_hash([
                {"name": x.get("name"), "format": x.get("format"), "url_type": x.get("url_type")}
                for x in resources
            ]) if resources else None,
        )
    except Exception as exc:
        return base_result(source, error_type=classify_error(exc), error=str(exc))


def discover_links(base_url, html):
    soup = BeautifulSoup(html, "html.parser")
    data_ext = re.compile(r"\.(json|geojson|csv|zip|7z|xml|xlsx|shp|gdb|kml)(?:$|\?)", re.I)
    service_token = re.compile(r"(FeatureServer|MapServer|/wms(?:$|\?)|/wfs(?:$|\?))", re.I)
    keyword = re.compile(r"(gtfs|ocds|download|descarga)", re.I)

    found = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        label = a.get_text(" ", strip=True)
        absolute = urljoin(base_url, href)

        # No considerar cambios visuales de la página como "recursos".
        low = absolute.lower()
        if "contrast=" in low or "width=" in low:
            continue

        if data_ext.search(absolute) or service_token.search(absolute) or keyword.search(href + " " + label):
            if absolute not in found:
                found.append(absolute)

    return found[:60]


def probe_download_catalog(source, timeout):
    try:
        r, latency = request_get(source["url"], timeout=timeout)
        http = r.status_code
        ctype = r.headers.get("content-type", "")
        r.raise_for_status()
        links = discover_links(r.url, r.text)
        return base_result(
            source,
            technical_status="OK" if links else "DEGRADED",
            http_status=http,
            latency_ms=latency,
            content_type=ctype,
            resource_count=len(links),
            sample_resource=links[0] if links else None,
            discovered_links=links,
            schema_hash=stable_hash(links) if links else None,
            error=None if links else "Página disponible, pero no se descubrieron enlaces de datos con los patrones del prototipo.",
        )
    except Exception as exc:
        return base_result(source, error_type=classify_error(exc), error=str(exc))


def probe_catalog_search(source, timeout):
    try:
        r, latency = request_get(source["url"], timeout=timeout)
        r.raise_for_status()
        text = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)
        m = re.search(r"Descubre\s+([\d\.]+)\s+datos territoriales", text, re.I)
        count = int(m.group(1).replace(".", "")) if m else None
        return base_result(
            source,
            technical_status="OK",
            http_status=r.status_code,
            latency_ms=latency,
            content_type=r.headers.get("content-type", ""),
            resource_count=count,
            service_name="Geoportal IDE Chile",
            error=None if count is not None else "Catálogo respondió; no se pudo extraer el conteo de datasets.",
        )
    except Exception as exc:
        return base_result(source, error_type=classify_error(exc), error=str(exc))


def probe_web(source, timeout):
    try:
        r, latency = request_get(source["url"], timeout=timeout, stream=True)
        http = r.status_code
        ctype = r.headers.get("content-type", "")
        r.raise_for_status()
        chunk = next(r.iter_content(chunk_size=4096), b"")
        return base_result(
            source,
            technical_status="OK" if chunk else "DEGRADED",
            http_status=http,
            latency_ms=latency,
            content_type=ctype,
            error=None if chunk else "Respuesta vacía.",
        )
    except Exception as exc:
        return base_result(source, error_type=classify_error(exc), error=str(exc))


def probe_auth_portal(source, timeout):
    result = probe_web(source, timeout)
    if result.technical_status == "OK":
        result.technical_status = "AUTH_REQUIRED"
        result.error = "Portal disponible. La API requiere credenciales; no se ejecutó un endpoint autenticado."
    return result


def probe_unconfigured(source):
    return base_result(
        source,
        technical_status="NOT_CONFIGURED",
        error=source.get("note"),
    )



def probe_chilecompra_ocds(source, timeout):
    """Canary liviana contra los 3 endpoints OCDS públicos."""
    try:
        from datetime import datetime
        now = datetime.now()
        year = now.year
        month = f"{now.month:02d}"

        base = source["url"].rstrip("/")
        paths = [
            ("licitacion", f"listaOCDSAgnoMes/{year}/{month}/0/1"),
            ("trato_directo", f"listaOCDSAgnoMesTratoDirecto/{year}/{month}/0/1"),
            ("convenio_marco", f"listaOCDSAgnoMesConvenio/{year}/{month}/0/1"),
        ]

        successes = []
        links = []
        total_latency = 0
        last_http = None
        last_ctype = None
        failures = []

        for label, path in paths:
            url = f"{base}/{path}"
            links.append(url)
            try:
                r, latency = request_get(url, timeout=timeout)
                total_latency += latency
                last_http = r.status_code
                last_ctype = r.headers.get("content-type", "")
                r.raise_for_status()
                payload = r.json()
                successes.append(label)
            except Exception as exc:
                failures.append(f"{label}: {exc}")

        if not successes:
            raise RuntimeError("Ninguno de los tres endpoints OCDS respondió correctamente. " + " | ".join(failures))

        status = "OK" if len(successes) == len(paths) else "DEGRADED"
        return base_result(
            source,
            technical_status=status,
            http_status=last_http,
            latency_ms=total_latency,
            content_type=last_ctype,
            service_name="ChileCompra OCDS",
            resource_count=len(successes),
            sample_resource=successes[0],
            discovered_links=links,
            schema_hash=stable_hash(successes),
            error_type=None if status == "OK" else "PARTIAL",
            error=None if status == "OK" else " | ".join(failures),
        )
    except Exception as exc:
        return base_result(source, error_type=classify_error(exc), error=str(exc))


def probe_source(source, timeout=DEFAULT_TIMEOUT):
    kind = source.get("kind")
    if not source.get("url") or kind == "unconfigured":
        return probe_unconfigured(source)
    if kind in ("arcgis_service", "arcgis_layer"):
        return probe_arcgis(source, timeout)
    if kind == "wms":
        return probe_wms(source, timeout)
    if kind == "wfs":
        return probe_wfs(source, timeout)
    if kind == "ckan_package":
        return probe_ckan(source, timeout)
    if kind == "chilecompra_ocds":
        return probe_chilecompra_ocds(source, timeout)
    if kind == "download_catalog":
        return probe_download_catalog(source, timeout)
    if kind == "catalog_search":
        return probe_catalog_search(source, timeout)
    if kind == "auth_portal":
        return probe_auth_portal(source, timeout)
    if kind in ("web_page", "binary_probe"):
        return probe_web(source, timeout)
    return base_result(source, error=f"Tipo de probe no soportado: {kind}")


def health_state(result: ProbeResult | Dict[str, Any]) -> Dict[str, Any]:
    data = result.to_dict() if isinstance(result, ProbeResult) else result
    status = data.get("technical_status")
    error_type = data.get("error_type")
    http_status = data.get("http_status")
    latency = data.get("latency_ms")

    if status == "NOT_CONFIGURED":
        health = "not_configured"
    elif http_status == 429 or error_type == "HTTP_429":
        health = "rate_limited"
    elif status == "AUTH_REQUIRED" or error_type in {"TLS_SSL"}:
        health = "auth_error" if status == "AUTH_REQUIRED" else "unknown"
    elif error_type == "TIMEOUT":
        health = "down"
    elif status == "OK" and latency is not None and latency > 5000:
        health = "slow"
    elif status == "DEGRADED":
        health = "slow" if latency is not None else "unknown"
    elif status == "OK":
        health = "healthy"
    elif status == "SOURCE_ERROR":
        health = "down"
    else:
        health = "unknown"

    return {
        "source_id": data.get("source_id"),
        "status": health,
        "latency_ms": latency,
        "checked_at": data.get("checked_at"),
        "technical_status": status,
        "error_type": error_type,
        "error": data.get("error"),
    }
