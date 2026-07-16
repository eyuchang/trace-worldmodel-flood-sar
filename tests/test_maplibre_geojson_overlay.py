from pathlib import Path


STATIC = Path(__file__).resolve().parents[1] / "src" / "trace_jepa" / "workbench" / "static"


def test_maplibre_overlay_assets_are_loaded_in_order() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "maplibre-gl@5.24.0/dist/maplibre-gl.js" in html
    assert html.index("maplibre-gl@5.24.0/dist/maplibre-gl.js") < html.index(
        "/static/maplibre_overlays.js"
    )
    assert html.index("/static/maplibre_overlays.js") < html.index("/static/app.js")
    assert 'id="map"' in html
    assert 'id="mapLoadStatus"' in html
    assert 'rel="icon"' in html


def test_overlay_uses_live_geojson_sources_and_safe_expressions() -> None:
    javascript = (STATIC / "maplibre_overlays.js").read_text(encoding="utf-8")
    for source_name in (
        "trace-flood",
        "trace-routes",
        "trace-authorized-paths",
        "trace-hazards",
        "trace-incidents",
        "trace-assets",
        "trace-locations",
    ):
        assert source_name in javascript
    assert ".setData(data)" in javascript
    assert "localToLngLat" in javascript
    assert '["coalesce"' in javascript
    assert "routeVisualStatus" in javascript
    assert "edgeVisualStatus" in javascript


def test_display_adapter_does_not_replace_simulator_navigation() -> None:
    javascript = (STATIC / "maplibre_overlays.js").read_text(encoding="utf-8")
    assert "path_segments" in javascript
    assert "segment.from_position" in javascript
    assert "segment.to_position" in javascript
    assert "planning still uses local graph coordinates" in (
        STATIC / "index.html"
    ).read_text(encoding="utf-8")
