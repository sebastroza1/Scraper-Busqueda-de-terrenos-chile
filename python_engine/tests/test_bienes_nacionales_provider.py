from __future__ import annotations

import zipfile
from io import BytesIO

import httpx
import pytest

from landfinder.connectors.auctions.bienes_nacionales import BienesNacionalesProvider
from landfinder.connectors.base import SearchQuery


@pytest.mark.asyncio
async def test_bienes_nacionales_discovers_real_asset_shape_from_official_html() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/licitaciones":
            return httpx.Response(
                200,
                text="""
                <a href="/licitacion/el-salado-mz-4-lote-5">El Salado</a>
                """,
            )
        if request.url.path == "/licitacion/el-salado-mz-4-lote-5":
            return httpx.Response(200, text=_detail_html())
        if request.url.path.endswith("F-2026-S1-KMZ-009.kmz"):
            return httpx.Response(200, content=_kmz_bytes())
        raise AssertionError(str(request.url))

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://licitaciones.mbienes.gob.cl",
    ) as client:
        provider = BienesNacionalesProvider(client=client)
        result = await provider.discover(SearchQuery(search_sources=["bienes_nacionales"]))

    assert len(result.raw_records) == 1
    record = result.raw_records[0]
    landfinder = record["raw_payload"]["landfinder"]
    assert record["external_id"] == "L-2026-S1-009"
    assert record["title"] == "El Salado Mz. 4 Lote 5"
    assert record["region_raw"] == "Atacama"
    assert record["commune_raw"] == "Chañaral"
    assert record["area_raw"] == "7100.00 m2"
    assert record["price_raw"] == "UF 142,00"
    assert landfinder["procurement_classification"] == "PROPERTY_FOR_SALE"
    assert landfinder["surface_context"] == "PARCEL_AREA"
    assert landfinder["geometry_source"] == "BIENES_NACIONALES_KMZ"
    assert landfinder["parcel_geometry"]["type"] == "Polygon"
    assert any(document["document_type"] == "KMZ" for document in landfinder["documents"])


@pytest.mark.asyncio
async def test_bienes_nacionales_geometry_stays_attached_to_external_id_when_reordered() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/licitaciones":
            return httpx.Response(
                200,
                text="""
                <a href="/licitacion/lote-b">Lote B</a>
                <a href="/licitacion/lote-a">Lote A</a>
                """,
            )
        if request.url.path == "/licitacion/lote-a":
            return httpx.Response(
                200,
                text=_detail_html_for("L-2026-S1-101", "Lote A", "a.kmz"),
            )
        if request.url.path == "/licitacion/lote-b":
            return httpx.Response(
                200,
                text=_detail_html_for("L-2026-S1-102", "Lote B", "b.kmz"),
            )
        if request.url.path.endswith("a.kmz"):
            return httpx.Response(200, content=_kmz_bytes_for(-70.50, -26.37))
        if request.url.path.endswith("b.kmz"):
            return httpx.Response(200, content=_kmz_bytes_for(-68.90, -22.47))
        raise AssertionError(str(request.url))

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://licitaciones.mbienes.gob.cl",
    ) as client:
        result = await BienesNacionalesProvider(client=client).discover(
            SearchQuery(search_sources=["bienes_nacionales"])
        )

    geometries = {
        record["external_id"]: record["raw_payload"]["landfinder"]["parcel_geometry"]
        for record in result.raw_records
    }
    assert geometries["L-2026-S1-101"]["coordinates"][0][0][0] == pytest.approx(-70.50)
    assert geometries["L-2026-S1-102"]["coordinates"][0][0][0] == pytest.approx(-68.90)


@pytest.mark.asyncio
async def test_bienes_nacionales_prefers_kmz_when_kml_and_kmz_are_linked() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/licitaciones":
            return httpx.Response(
                200,
                text="""<a href="/licitacion/lote-con-kml-y-kmz">Lote</a>""",
            )
        if request.url.path == "/licitacion/lote-con-kml-y-kmz":
            return httpx.Response(
                200,
                text=_detail_html_for_spatial_docs(
                    "L-2026-S1-016",
                    "El Salado Mz. 11 Lote 2",
                    "wrong.kml",
                    "right.kmz",
                ),
            )
        if request.url.path.endswith("wrong.kml"):
            return httpx.Response(200, content=_kml_bytes_for(-68.90, -22.47))
        if request.url.path.endswith("right.kmz"):
            return httpx.Response(200, content=_kmz_bytes_for(-70.50, -26.37))
        raise AssertionError(str(request.url))

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://licitaciones.mbienes.gob.cl",
    ) as client:
        result = await BienesNacionalesProvider(client=client).discover(
            SearchQuery(search_sources=["bienes_nacionales"])
        )

    landfinder = result.raw_records[0]["raw_payload"]["landfinder"]
    assert landfinder["geometry_source"] == "BIENES_NACIONALES_KMZ"
    assert landfinder["parcel_geometry"]["coordinates"][0][0][0] == pytest.approx(-70.50)


def _detail_html() -> str:
    return """
    <main>
      <div>Abierta</div>
      <div>L-2026-S1-009</div>
      <h1>El Salado Mz. 4 Lote 5</h1>
      <div>Industrial Actuales</div>
      <p>Región: Atacama</p>
      <p>Provincia: Chañaral</p>
      <p>Comuna: Chañaral</p>
      <p>Modalidad: Venta</p>
      <p>Superficie: 7100.00 m2</p>
      <p>ID Catastral: 865510</p>
      <p>ID Bienes: 160</p>
      <h2>Instrumento de Planificación Territorial</h2>
      <p>PRI</p>
      <h2>Descripción</h2>
      <p>Inmueble ubicado en El Salado Mz. 4 Lote 5, comuna de Chañaral,
      Región de Atacama. Valor comercial mínimo: 142,00 UF.</p>
      <h2>Uso permitido</h2>
      <p>Actividades Productivas, Infraestructura, Áreas Verdes, Espacio Público</p>
      <h2>Uso prohibido</h2>
      <p>Todos Los No Indicados Como Permitidos</p>
      <a href="/api/storage/L-2026-S1-009_99.pdf">L-2026-S1-009_99.pdf</a>
      <a href="/api/storage/L-2026-S1-009.pdf">L-2026-S1-009.pdf</a>
      <a href="https://geoportal.cl/mbn/dashboard/1022">Ver en el visor GeoNodo</a>
      <a href="/api/storage/F-2026-S1-KMZ-009.kmz">F-2026-S1-KMZ-009.kmz</a>
    </main>
    """


def _detail_html_for(code: str, title: str, kmz: str) -> str:
    return f"""
    <main>
      <div>Abierta</div>
      <div>{code}</div>
      <h1>{title}</h1>
      <p>Región: Atacama</p>
      <p>Provincia: Chañaral</p>
      <p>Comuna: Chañaral</p>
      <p>Modalidad: Venta</p>
      <p>Superficie: 5000.00 m2</p>
      <h2>Descripción</h2>
      <p>{title}, comuna de Chañaral. Valor comercial mínimo: 100,00 UF.</p>
      <a href="/api/storage/{kmz}">{kmz}</a>
    </main>
    """


def _detail_html_for_spatial_docs(code: str, title: str, kml: str, kmz: str) -> str:
    return f"""
    <main>
      <div>{code}</div>
      <h1>{title}</h1>
      <p>Región: Atacama</p>
      <p>Provincia: Chañaral</p>
      <p>Comuna: Chañaral</p>
      <p>Modalidad: Venta</p>
      <p>Superficie: 5000.00 m2</p>
      <h2>Descripción</h2>
      <p>{title}, comuna de Chañaral. Valor comercial mínimo: 100,00 UF.</p>
      <a href="/api/storage/{kml}">{kml}</a>
      <a href="/api/storage/{kmz}">{kmz}</a>
    </main>
    """


def _kml_bytes_for(lon: float, lat: float) -> bytes:
    return f"""
    <kml xmlns="http://www.opengis.net/kml/2.2">
      <Document>
        <Placemark>
          <Polygon>
            <outerBoundaryIs>
              <LinearRing>
                <coordinates>
                  {lon},{lat},0 {lon + 0.01},{lat},0 {lon + 0.01},{lat + 0.01},0
                  {lon},{lat + 0.01},0 {lon},{lat},0
                </coordinates>
              </LinearRing>
            </outerBoundaryIs>
          </Polygon>
        </Placemark>
      </Document>
    </kml>
    """.encode()


def _kmz_bytes() -> bytes:
    kml = b"""
    <kml xmlns="http://www.opengis.net/kml/2.2">
      <Document>
        <Placemark>
          <Polygon>
            <outerBoundaryIs>
              <LinearRing>
                <coordinates>
                  -70.15,-26.35,0 -70.14,-26.35,0 -70.14,-26.34,0
                  -70.15,-26.34,0 -70.15,-26.35,0
                </coordinates>
              </LinearRing>
            </outerBoundaryIs>
          </Polygon>
        </Placemark>
      </Document>
    </kml>
    """
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("doc.kml", kml)
    return buffer.getvalue()


def _kmz_bytes_for(lon: float, lat: float) -> bytes:
    kml = f"""
    <kml xmlns="http://www.opengis.net/kml/2.2">
      <Document>
        <Placemark>
          <Polygon>
            <outerBoundaryIs>
              <LinearRing>
                <coordinates>
                  {lon},{lat},0 {lon + 0.01},{lat},0 {lon + 0.01},{lat + 0.01},0
                  {lon},{lat + 0.01},0 {lon},{lat},0
                </coordinates>
              </LinearRing>
            </outerBoundaryIs>
          </Polygon>
        </Placemark>
      </Document>
    </kml>
    """.encode()
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("doc.kml", kml)
    return buffer.getvalue()
