---
name: geo-mapping
description: "Create publication-quality scientific maps for geoscience papers — choropleth, hillshade/terrain, vector field, multi-panel layouts. Uses QGIS via `/qgis-mcp` if available; falls back to Python (geopandas, cartopy, rasterio, matplotlib). Use when the research needs a geospatial figure, map, or remote sensing visualisation."
argument-hint: "[map-description or data-path]"
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, WebSearch, WebFetch, Skill(qgis-mcp)
---

# Geo-Mapping: Scientific Mapping for Geoscience Research

Map request: $ARGUMENTS

## Purpose

Create publication-quality scientific maps for geoscience papers, posters, presentations, or supplementary materials. This skill supports the full pipeline from raw geospatial data to a print-ready map figure.

**Invoke when the task asks for:**
- a map, spatial visualisation, or geographic figure
- a choropleth, hillshade terrain map, or vector field map
- a multi-panel map layout with inset maps
- a remote sensing composite or classification map
- any figure with coastlines, administrative boundaries, graticules, scale bar, north arrow, or legend

**Relationship:**
- Pre-process spatial data and validate CRS using `/geo-awareness`
- For non-map geoscience figures (time series plots, correlation matrices, architecture diagrams) use standard ARIS plotting skills
- For generic geospatial analysis (not figure creation) use `/qgis-mcp`

## Constants

- **MAP_DPI = 300** — minimum resolution for publication
- **OUTPUT_DIR = "maps"** — maps are written to `maps/` in the current project
- **VECTOR_FORMATS:** `.pdf` (vector, preferred for paper), `.png` (raster, for preview)
- **MAP_SCALE_BAR = true** — include a scale bar on every map
- **MAP_NORTH_ARROW = true** — include north arrow on every map
- **MAP_LEGEND = true** — include a legend when the map uses symbology
- **CRS_DECLARATION_REQUIRED = true** — every output map must declare its CRS

---

## Workflow

### Step 1: Understand the Data

Determine what spatial data is available and what the map should communicate:

- **Data format(s):** vector (Shapefile, GeoPackage, GeoJSON) or raster (GeoTIFF, NetCDF)
- **Geometry type:** points, lines, polygons, continuous rasters
- **Variables / attributes:** what to map (e.g. population density, elevation, temperature anomaly, land cover class)
- **CRS of input data:** verify before any reprojection
- **Desired output:** paper figure, presentation slide, interactive web map, supplementary material

### Step 2: Choose the Map Type

| Map Type | Data Suitable | Geoscience Subdomain |
|---|---|---|
| **Choropleth** | Polygon-aggregated continuous or categorical | Any; most common (demographics, hazards, climate zones) |
| **Graduated symbol** | Point data with magnitude | Seismology (earthquake magnitudes), geochemistry (sample concentrations) |
| **Dot density** | Point events | Ecology (species occurrences), epidemiology |
| **Hillshade / terrain** | DEM raster | Geomorphology, hydrology, structural geology |
| **Vector field** | U/V components | Meteorology (wind), oceanography (currents), geophysics (magnetic) |
| **Heatmap (KDE)** | Point density surface | Hotspot analysis, crime mapping, point cluster visualisation |
| **False-colour composite** | Multi-band satellite | Remote sensing (NIR-R-G, SWIR-NIR-R composites) |
| **Classification map** | Thematic raster | Land cover, geological units, soil types |
| **Multi-panel layout** | Multiple inputs | Compare time steps, regions, methods; context + detail maps |
| **Change detection** | Bi-temporal imagery | Deforestation, urban expansion, flood mapping |

### Step 3: Primary Path — QGIS via `/qgis-mcp`

Check if QGIS MCP is available:

```bash
claude mcp list | grep qgis
```

If QGIS is running with the plugin server started:

#### 3a. Load or create a QGIS project

```
/qgis-mcp "Load data from ./data/ and create a map project"
```

The `/qgis-mcp` skill handles layer loading (`add_vector_layer`, `add_raster_layer`), project management (`create_new_project`, `load_project`), and QGIS connectivity.

#### 3b. Style the layers

Use `execute_processing` or `execute_code` for QGIS-native styling:

- **Choropleth:** `qgis:setlayerstyle` or PyQGIS `QgsGraduatedSymbolRenderer`
- **Hillshade:** `gdal:hillshade` processing algorithm
- **Colour ramp:** use colour-blind-friendly sequential (YlOrRd, viridis) or diverging (RdYlBu, spectral) ramps — see `[geo-awareness]` for guidance
- **Label placement:** use `qgis:setlayerlabelsettings` or PyQGIS `QgsPalLayerSettings`

#### 3c. Create the print layout

Use `execute_code` to set up a QGIS `QgsLayout` with:

- **Map item(s):** main map, optional inset map(s) for context/location
- **Scale bar:** `QgsScaleBar` — ensure units match CRS
- **North arrow:** `QgsLayoutItemPicture` with north arrow SVG
- **Legend:** `QgsLayoutItemLegend` — group, ungroup, and rename items
- **Graticule:** `QgsLayoutItemMapGrid` — lat/lon grid with annotations
- **Size:** match journal column width (e.g. 84 mm single-column, 174 mm double-column)
- **Export:** `QgsLayoutExporter` to `.pdf` (vector) or `.png` (300+ DPI)

#### 3d. Render and export

```
/qgis-mcp "Render the map to maps/output.png and save the QGIS project"
```

Use `render_map` for canvas view, or `execute_code` + `QgsLayoutExporter` for layout-based export.

### Step 4: Fallback — Python Geoscience Plotting

If QGIS is not available, use Python:

```bash
# Check available packages
python3 -c "import geopandas; import cartopy; import rasterio; import matplotlib; print('Python GIS stack OK')" 2>&1 || pip install geopandas cartopy rasterio matplotlib contextily
```

#### Example per map type

**Choropleth (geopandas + matplotlib):**
```python
import geopandas as gpd
import matplotlib.pyplot as plt

gdf = gpd.read_file("data/admin_boundaries.shp")
fig, ax = plt.subplots(figsize=(6, 4))
gdf.plot(column="variable", cmap="viridis", legend=True, ax=ax,
         edgecolor="0.8", linewidth=0.3)
ax.set_title("Choropleth of Variable")
ax.axis("off")  # remove axis ticks for map
plt.savefig("maps/choropleth.pdf", bbox_inches="tight")
```

**Terrain / hillshade (rasterio + matplotlib):**
```python
import rasterio
from rasterio.plot import show
import matplotlib.pyplot as plt

with rasterio.open("data/dem.tif") as src:
    fig, ax = plt.subplots(figsize=(6, 4))
    show(src, cmap="terrain", ax=ax)
    ax.set_title("Elevation (DEM)")
plt.savefig("maps/terrain.pdf", bbox_inches="tight")
```

**Multi-panel map with cartopy:**
```python
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature

proj = ccrs.PlateCarree()  # or ccrs.UTM(zone=50)
fig, axes = plt.subplots(1, 2, figsize=(8, 4),
                         subplot_kw={"projection": proj})
for ax in axes:
    ax.add_feature(cfeature.COASTLINE, linewidth=0.5)
    ax.add_feature(cfeature.BORDERS, linewidth=0.3)
    ax.gridlines(draw_labels=True, linewidth=0.2)
    # ... plot data on each subplot
plt.savefig("maps/multi-panel.pdf", bbox_inches="tight")
```

**Contextily basemap:**
```python
import geopandas as gpd
import contextily as ctx

gdf = gpd.read_file("data/study_area.shp").to_crs(epsg=3857)
ax = gdf.plot(figsize=(6, 4), alpha=0.5, edgecolor="k")
ctx.add_basemap(ax, source=ctx.providers.OpenStreetMap.Mapnik)
ax.axis("off")
plt.savefig("maps/with-basemap.pdf", bbox_inches="tight")
```

#### Layout helpers

```python
# Scale bar function (matplotlib_scalebar)
# pip install matplotlib-scalebar
from matplotlib_scalebar.scalebar import ScaleBar
ax.add_artist(ScaleBar(dx=1, units="m"))  # dx = map units per pixel

# North arrow
# Add manually: use an arrow annotation at map edge
```

### Step 5: CRS Verification

Before final export, verify:

1. **All layers share a consistent CRS** — if not, reproject to the project CRS
2. **Distance-based maps** (buffers, scale bars) use a projected CRS appropriate for the location
3. **Area-based maps** (density, zonal stats) use an equal-area projection
4. **Global maps** use Robinson, Winkel Tripel, or equirectangular with latitude-dependent scale bar

**Declare the CRS in the map metadata or caption:** e.g. "All maps in UTM Zone 50N (EPSG:32650)".

### Step 6: Output

Write all map outputs to `maps/`:

```
maps/
├── map-main.pdf         # Vector (paper figure)
├── map-main.png         # Raster (300 DPI, preview)
├── map-inset.pdf        # Inset / context map
├── project.qgz          # QGIS project (if using QGIS path)
└── legend.txt           # (optional) legend description
```

Every output file name should indicate content and CRS. Caption template:

> **Figure X.** [Descriptive title]. Base map: [source]. CRS: [EPSG:xxxx]. Scale bar valid at map centre.

---

## Map Types by Geoscience Subdomain

### Geology

| Map | Data | QGIS Path | Python Path |
|---|---|---|---|
| Lithological | Polygon lithology units | Graduated renderer + geological colour scheme | geopandas + cmap from `cmasher.geologic` |
| Structural | Strike/dip point data | Point symbols with rotation attribute | matplotlib quiver |
| Cross-section | DEM + section line | Profile tool plugin | `skimage` or `matplotlib` along transect |

### Hydrology

| Map | Data | QGIS Path | Python Path |
|---|---|---|---|
| Watershed/ basin | DEM → flow accumulation → watershed | `grass:r.watershed` in Processing | `pysheds` or `whitebox` |
| Groundwater contours | Well point measurements | Interpolation (TIN, IDW) → contour | `scipy.griddata` + `matplotlib.contour` |
| Flood extent | Satellite imagery or model output | Threshold classification | rasterio threshold + geopandas polygonise |

### Climatology

| Map | Data | QGIS Path | Python Path |
|---|---|---|---|
| Isopleth (contour) | Gridded T/P data | Contour from raster | `cartopy.contourf` on xarray |
| Anomaly map | Observed − climatology mean | Raster calculator | xarray difference + cartopy |
| Ensemble spread | Multi-model GCM outputs | Raster stack statistics | xarray std + cartopy |

### Ecology

| Map | Data | QGIS Path | Python Path |
|---|---|---|---|
| Species distribution | Point occurrences + environmental layers | MaxEnt plugin (external) | `geopandas.plot` + basemap |
| NDVI time series | Multi-date NDVI rasters | Raster time manager | xarray + cartopy (1 panel per date) |
| Land cover | Thematic class raster | Palette-based renderer | `rasterio.plot.show` with `cmap` |

### Remote Sensing

| Map | Data | QGIS Path | Python Path |
|---|---|---|---|
| False-colour composite | Multi-band GeoTIFF | Band set (R=4/NIR, G=3/R, B=2/G) | rasterio plot with `rgb=` |
| Change detection | Bi-temporal imagery | Raster calculator → binary | Difference raster + geopandas.vectorise |
| Classification | ML model output raster | Palette renderer | matplotlib imshow with ListedColormap |

### Geophysics

| Map | Data | QGIS Path | Python Path |
|---|---|---|---|
| Gravity/magnetic anomaly | Gridded XYZ data | TIN interpolation → raster → colour | `scipy.griddata` + matplotlib |
| Seismic sections | SEG-Y or interpreted horizon | Custom plugin or mesh | matplotlib profile plot |
| Magnetotelluric | Impedance tensors | Vector field arrows | matplotlib quiver + colour |

---

## Edge Cases

| Issue | Handling |
|---|---|
| **Data spans multiple UTM zones** | Use Lambert conformal conic or Albers equal-area for the study area; avoid any single UTM zone |
| **Offline / no basemap tiles** | Use Natural Earth (bundled shapefiles) or skip basemap; never use placeholders |
| **Raster/vector resolution mismatch** | Resample raster to match vector scale; state the effective resolution |
| **Colour-blind accessibility** | Use viridis/cividis for sequential maps; colorbrewer diverging for bipolar; avoid red-green |
| **Global map distortion** | Use Robinson or Winkel Tripel; never use Web Mercator for display |
| **Zero values in log-scale** | Add a small offset or use arcsinh transformation; note in caption |

---

## Key Rules

- **Every map must declare its CRS** in the caption or metadata. A map without a CRS is not reproducible.
- **Every distance-based map must use a projected CRS** appropriate to the region.
- **Use colour-blind-friendly palettes** by default (viridis, cividis, colorbrewer diverging).
- **Minimum 300 DPI** for raster exports; vector PDF for submissions.
- **Never use Web Mercator (EPSG:3857)** for any map destined for publication — it distorts area catastrophically.
- **For paper submissions**, verify the journal's figure requirements (column width, colour costs, resolution).
