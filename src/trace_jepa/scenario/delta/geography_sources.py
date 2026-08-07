from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class GeographySourceDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    title: str
    landing_page_locator: str
    retrieval_locator: str | None
    file_name: str
    snapshot_format: Literal["json", "geojson", "html"]
    expected_media_types: tuple[str, ...] = Field(min_length=1)
    source_tier: str
    status: str
    use: str
    license_name: str
    license_locator: str
    redistribution_status: str = "clipped-government-snapshot-review-complete"


SACRAMENTO_DISTRICTS_URL = (
    "https://mapservices.gis.saccounty.net/ArcGIS/rest/services/"
    "SERVICE_DISTRICTS/MapServer/7/query"
    "?where=DISTRICT%20IN%20(%27Andrus%20Island%20407%27,"
    "%27Lower%20Andrus%20Island%20317%27,"
    "%27Upper%20Andrus%20Island%20556%27,"
    "%27Brannan%20Island%202067%27)"
    "&outFields=*&returnGeometry=true&outSR=4326&f=geojson"
)
DWR_LMA_URL = (
    "https://gis.water.ca.gov/arcgis/rest/services/Boundaries/"
    "i03_Local_Maintenance_Areas_Flood_Protection/MapServer/0?f=pjson"
)
CENSUS_ISLETON_URL = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/"
    "Places_CouSub_ConCity_SubMCD/MapServer/4/query"
    "?where=STATE%3D%2706%27%20AND%20BASENAME%3D%27Isleton%27"
    "&outFields=OBJECTID,GEOID,STATE,PLACE,BASENAME,NAME,AREALAND,AREAWATER,"
    "CENTLAT,CENTLON,INTPTLAT,INTPTLON"
    "&returnGeometry=true&outSR=4326&f=geojson"
)
CALTRANS_BRIDGES_URL = (
    "https://caltrans-gis.dot.ca.gov/arcgis/rest/services/CHhighway/"
    "State_Highway_Bridges/FeatureServer/0/query"
    "?where=OBJECTID%20IN%20(2255,2286)"
    "&outFields=OBJECTID,DIST,CO,PM,BRIDGE,CITY,LAT,LON,NAME,LOC,YRBLT,FAC,"
    "DESIGN_MAIN,MATERIAL_MAIN,INTERSEC,RTE,DATA_EXTRACTED"
    "&returnGeometry=true&outSR=4326&f=geojson"
)
USGS_HYDROGRAPHY_URL = (
    "https://hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer/6/query"
    "?where=GNIS_NAME%20IN%20(%27Sacramento%20River%27,"
    "%27Three%20Mile%20Slough%27,%27Threemile%20Slough%27,"
    "%27Georgiana%20Slough%27)"
    "&geometry=-121.75%2C38.05%2C-121.45%2C38.25"
    "&geometryType=esriGeometryEnvelope&inSR=4326"
    "&spatialRel=esriSpatialRelIntersects"
    "&outFields=OBJECTID,PERMANENT_IDENTIFIER,GNIS_NAME,FTYPE,FCODE,"
    "REACHCODE,RESOLUTION"
    "&returnGeometry=true&outSR=4326&f=geojson"
)
STATE_PARKS_BRANNAN_URL = (
    "https://services2.arcgis.com/AhxrK3F6WM8ECvDi/arcgis/rest/services/"
    "ParkBoundaries/FeatureServer/0/query"
    "?where=UNITNAME%20LIKE%20%27%25Brannan%25%27"
    "&outFields=FID,UNITNAME,GISID,SUBTYPE,UNITNBR,GlobalID"
    "&returnGeometry=true&outSR=4326&f=geojson"
)
ISLETON_FIRE_URL = "https://www.cityofisleton.com/fire-department"
ISLETON_FIRE_GEOCODE_URL = (
    "https://nominatim.openstreetmap.org/search"
    "?q=101%202nd%20Street%2C%20Isleton%2C%20CA%2095641&format=jsonv2"
)
DBW_FACILITIES_URL = "https://dbw.parks.ca.gov/BoatingFacilities/County/Sacramento"
CDEC_RVB_URL = "https://cdec.water.ca.gov/dynamicapp/staMeta?station_id=RVB"
CDEC_MRU_URL = "https://cdec.water.ca.gov/dynamicapp/staMeta?station_id=MRU"
CDEC_FPT_URL = "https://cdec.water.ca.gov/dynamicapp/staMeta?station_id=FPT"
DWR_DEM_METADATA_URL = (
    "https://data.cnra.ca.gov/api/3/action/package_show"
    "?id=san-francisco-bay-and-sacramento-san-joaquin-delta-dem-for-modeling-"
    "version-4-3"
)
DWR_DEM_ARCHIVE_URL = (
    "https://data.cnra.ca.gov/dataset/f902e012-7d8d-429c-8a1a-2bf5b4312532/"
    "resource/d10040a8-4880-4f0e-90e7-86f57556bd9d/download/"
    "dem_delta_10m_20250312.zip"
)


GEOGRAPHY_SOURCE_DEFINITIONS = [
    GeographySourceDefinition(
        source_id="sacramento-county-drainage-districts-2026-08-05",
        title="Sacramento County drainage districts for Andrus and Brannan",
        landing_page_locator=(
            "https://mapservices.gis.saccounty.net/ArcGIS/rest/services/"
            "SERVICE_DISTRICTS/MapServer/7"
        ),
        retrieval_locator=SACRAMENTO_DISTRICTS_URL,
        file_name="sacramento_county_drainage_districts.geojson",
        snapshot_format="geojson",
        expected_media_types=("application/geo+json", "application/json", "text/plain"),
        source_tier="authoritative-local-government-gis",
        status="authoritative-operational-boundary-with-mapping-limitations",
        use="unioned island operational footprints and reclamation district identities",
        license_name="Sacramento County public GIS data",
        license_locator="https://data.saccounty.gov/pages/terms",
        redistribution_status="clipped-government-snapshot-with-source-attribution",
    ),
    GeographySourceDefinition(
        source_id="dwr-local-maintenance-areas-2026-08-05",
        title="DWR Local Maintenance Areas for flood protection",
        landing_page_locator=(
            "https://gis.water.ca.gov/arcgis/rest/services/Boundaries/"
            "i03_Local_Maintenance_Areas_Flood_Protection/MapServer/0"
        ),
        retrieval_locator=DWR_LMA_URL,
        file_name="dwr_local_maintenance_areas_metadata.json",
        snapshot_format="json",
        expected_media_types=("application/json", "text/plain"),
        source_tier="authoritative-state-government-gis",
        status="authoritative-crosscheck-variable-boundary-accuracy",
        use="crosscheck governance and combined Brannan-Andrus maintenance area",
        license_name="California public data",
        license_locator="https://gis.water.ca.gov/",
        redistribution_status="government-metadata-snapshot-with-source-attribution",
    ),
    GeographySourceDefinition(
        source_id="census-tiger-isleton-2025",
        title="2025 TIGERweb Incorporated Places: Isleton",
        landing_page_locator=(
            "https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html"
        ),
        retrieval_locator=CENSUS_ISLETON_URL,
        file_name="census_tiger_isleton.geojson",
        snapshot_format="geojson",
        expected_media_types=("application/geo+json", "application/json", "text/plain"),
        source_tier="authoritative-federal-administrative-boundary",
        status="authoritative-administrative-boundary",
        use="Isleton city boundary, GEOID, and centroid",
        license_name="United States public domain",
        license_locator="https://www.census.gov/data/developers/about/terms-of-service.html",
        redistribution_status="redistributable-united-states-public-domain",
    ),
    GeographySourceDefinition(
        source_id="caltrans-state-highway-bridges-2024",
        title="Caltrans State Highway Bridges inventory",
        landing_page_locator=(
            "https://gis.data.ca.gov/datasets/ea685fd702f840a7a751b12373d6249c_0/about"
        ),
        retrieval_locator=CALTRANS_BRIDGES_URL,
        file_name="caltrans_state_highway_bridges.geojson",
        snapshot_format="geojson",
        expected_media_types=("application/geo+json", "application/json", "text/plain"),
        source_tier="authoritative-state-infrastructure-inventory",
        status="inventory-extract-2024-03-12",
        use="XNG-03 and XNG-04 locations, route, and movable bridge design",
        license_name="No restrictions on public use",
        license_locator="https://gis.data.ca.gov/datasets/ea685fd702f840a7a751b12373d6249c_0/about",
        redistribution_status="redistributable-no-public-use-restrictions",
    ),
    GeographySourceDefinition(
        source_id="usgs-nhd-flowlines-2026-08-05",
        title="USGS National Hydrography Dataset flowlines",
        landing_page_locator="https://www.usgs.gov/national-hydrography/access-national-hydrography-products",
        retrieval_locator=USGS_HYDROGRAPHY_URL,
        file_name="usgs_nhd_flowlines.geojson",
        snapshot_format="geojson",
        expected_media_types=("application/geo+json", "application/json", "text/plain"),
        source_tier="authoritative-federal-hydrography",
        status="public-domain-live-service-snapshot",
        use="Sacramento River, Three Mile Slough, and Georgiana Slough geometry",
        license_name="United States public domain",
        license_locator="https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits",
        redistribution_status="redistributable-united-states-public-domain",
    ),
    GeographySourceDefinition(
        source_id="california-state-parks-brannan-2026-08-05",
        title="California State Parks Brannan Island unit boundary",
        landing_page_locator="https://www.parks.ca.gov/",
        retrieval_locator=STATE_PARKS_BRANNAN_URL,
        file_name="state_parks_brannan.geojson",
        snapshot_format="geojson",
        expected_media_types=("application/geo+json", "application/json", "text/plain"),
        source_tier="authoritative-state-recreation-gis",
        status="general-reference-boundary-not-property-survey",
        use="Brannan Island State Recreation Area facility anchor",
        license_name="California State Parks public GIS data",
        license_locator="https://www.parks.ca.gov/",
        redistribution_status="clipped-government-snapshot-with-source-attribution",
    ),
    GeographySourceDefinition(
        source_id="isleton-fire-department-2026-08-05",
        title="City of Isleton Fire Department",
        landing_page_locator=ISLETON_FIRE_URL,
        retrieval_locator=None,
        file_name="isleton_fire_department_record.json",
        snapshot_format="json",
        expected_media_types=("application/json",),
        source_tier="authoritative-local-agency-record",
        status="official-current-web-record",
        use="local fire station address and apparatus inventory",
        license_name="Project-authored factual extract from a public agency record",
        license_locator="https://www.cityofisleton.com/",
        redistribution_status="project-authored-factual-extract-upstream-page-not-committed",
    ),
    GeographySourceDefinition(
        source_id="osm-isleton-fire-geocode-2026-08-05",
        title="OpenStreetMap Nominatim geocode for 101 2nd Street",
        landing_page_locator="https://nominatim.openstreetmap.org/ui/search.html",
        retrieval_locator=ISLETON_FIRE_GEOCODE_URL,
        file_name="osm_isleton_fire_geocode.json",
        snapshot_format="json",
        expected_media_types=("application/json",),
        source_tier="community-sourced-secondary-geocode",
        status="secondary-location-anchor",
        use="approximate coordinate for the official fire station address",
        license_name="Open Data Commons Open Database License 1.0",
        license_locator="https://www.openstreetmap.org/copyright",
        redistribution_status="redistributable-with-odbl-attribution",
    ),
    GeographySourceDefinition(
        source_id="california-dbw-sacramento-facilities-2026-08-05",
        title="California Division of Boating and Waterways facilities",
        landing_page_locator=DBW_FACILITIES_URL,
        retrieval_locator=None,
        file_name="dbw_sacramento_boating_facilities_record.json",
        snapshot_format="json",
        expected_media_types=("application/json",),
        source_tier="authoritative-state-facility-directory",
        status="official-current-web-record",
        use="confirm Brannan Island SRA marina and launch capability",
        license_name="Project-authored factual extract from a public agency directory",
        license_locator="https://www.parks.ca.gov/",
        redistribution_status="project-authored-factual-extract-upstream-page-not-committed",
    ),
    GeographySourceDefinition(
        source_id="cdec-rvb-metadata-2026-08-05",
        title="CDEC metadata: Sacramento River at Rio Vista Bridge",
        landing_page_locator=CDEC_RVB_URL,
        retrieval_locator=None,
        file_name="cdec_rvb_metadata.html",
        snapshot_format="html",
        expected_media_types=("text/html",),
        source_tier="authoritative-operational-metadata",
        status="official-current-web-record",
        use="RVB station identity, location, datum, and stage definitions",
        license_name="California public data",
        license_locator="https://cdec.water.ca.gov/",
        redistribution_status="government-metadata-snapshot-with-source-attribution",
    ),
    GeographySourceDefinition(
        source_id="cdec-mru-metadata-2026-08-05",
        title="CDEC metadata: Middle River at Undine Road",
        landing_page_locator=CDEC_MRU_URL,
        retrieval_locator=None,
        file_name="cdec_mru_metadata.html",
        snapshot_format="html",
        expected_media_types=("text/html",),
        source_tier="authoritative-operational-metadata",
        status="official-current-web-record",
        use="MRU station identity and location; no operational thresholds",
        license_name="California public data",
        license_locator="https://cdec.water.ca.gov/",
        redistribution_status="government-metadata-snapshot-with-source-attribution",
    ),
    GeographySourceDefinition(
        source_id="cdec-fpt-metadata-2026-08-05",
        title="CDEC metadata: Sacramento River at Freeport",
        landing_page_locator=CDEC_FPT_URL,
        retrieval_locator=None,
        file_name="cdec_fpt_metadata.html",
        snapshot_format="html",
        expected_media_types=("text/html",),
        source_tier="authoritative-operational-metadata",
        status="official-current-web-record",
        use="FPT station identity and location; no operational thresholds",
        license_name="California public data",
        license_locator="https://cdec.water.ca.gov/",
        redistribution_status="government-metadata-snapshot-with-source-attribution",
    ),
    GeographySourceDefinition(
        source_id="dwr-bay-delta-dem-v4.3-metadata",
        title="DWR Bay-Delta DEM for Modeling version 4.3",
        landing_page_locator=(
            "https://data.cnra.ca.gov/dataset/"
            "san-francisco-bay-and-sacramento-san-joaquin-delta-dem-for-modeling-"
            "version-4-3"
        ),
        retrieval_locator=DWR_DEM_METADATA_URL,
        file_name="dwr_bay_delta_dem_v4_3_metadata.json",
        snapshot_format="json",
        expected_media_types=("application/json", "text/plain"),
        source_tier="authoritative-state-elevation-product",
        status="version-4.3-completed-2025-03",
        use="DEM version, datum, provenance, and Delta 10 m resource identity",
        license_name="License not specified; public access with required citation",
        license_locator=(
            "https://data.cnra.ca.gov/dataset/"
            "san-francisco-bay-and-sacramento-san-joaquin-delta-dem-for-modeling-"
            "version-4-3"
        ),
        redistribution_status="metadata-snapshot-only-upstream-binary-not-committed",
    ),
]
