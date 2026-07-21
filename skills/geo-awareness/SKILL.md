---
name: geo-awareness
description: "Geoscience domain awareness — CRS, spatial topology, earth system science, core spatial analysis techniques (Moran's I, GWR, KDE, Ripley's K, LISA, spatiotemporal analysis, remote sensing DL). Use when the research touches earth science, geography, geology, hydrology, climatology, ecology, remote sensing, or any geospatial data, so the LLM applies correct spatial reasoning instead of naive generic-ML assumptions."
argument-hint: "[research-topic-or-question] [— sources: <source-list>]"
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, WebSearch, WebFetch, Skill(qgis-mcp)
---

# Geo-Awareness: Geoscience Domain Awareness for ARIS Research

Research topic: $ARGUMENTS

## Purpose

Use this skill when the research involves any aspect of earth science or geospatial data. General LLMs — even capable ones — systematically overlook (or get wrong) foundational geoscience concepts when generating analyses, experiments, or papers. This skill provides the spatial reasoning layer ARIS needs to produce credible earth-science research.

**Invoke when the topic is about:**

- physical geography, geology, geomorphology, soil science
- hydrology, hydrogeology, water resources
- climatology, meteorology, atmospheric science
- ecology, biogeography, vegetation dynamics
- remote sensing, satellite imagery analysis
- geostatistics, spatial data science, geographic information science
- environmental science, natural hazards, global change

**If the centre of gravity is generic ML methodology without a spatial/earth-science context, fall back to general ARIS skills.**

## Constants

- **CRS_AWARE = true** — always treat data in its native CRS; do not silently assume WGS84.
- **CRS_JUSTIFICATION_REQUIRED** — any distance calculation, area measurement, or spatial operation must name the CRS used and justify why it is appropriate for the location and purpose.
- **OUTPUT_CRS_FORMAT = "EPSG:{code}"** — all CRS references in output must use the EPSG code.

## Relationship to Other ARIS Skills

`geo-awareness` provides the domain-knowledge layer that should be loaded alongside other skills when the subject is earth science:

| When using … | Apply geo-awareness's … |
|---|---|
| `/research-lit` | CRS-aware literature filtering, knowledge of earth-science-specific databases (AGU, EGU, GSA) |
| `/research-refine` | spatial constraints on methodology design, MAUP/edge-effect awareness |
| `/experiment-plan` | geospatial data prerequisites, resolution/scale considerations |
| `/paper-write` | geoscience writing conventions, CRS declaration in methods section |
| `/qgis-mcp` | domain-aware guidance for which spatial operations to run |
| `/geo-mapping` | CRS selection, projection rationale, map layout conventions |

---

## 1. Coordinate Reference System (CRS) Fundamentals

**Why this matters for LLMs:** The same pair of coordinates produces radically different distance and area measurements under different CRS. An LLM that silently treats all coordinates as flat Cartesian (Web Mercator EPSG:3857) will overestimate areas and distances away from the equator by orders of magnitude.

### 1.1 Geographic vs Projected CRS

| Type | EPSG Example | Unit | Distortion | Use For |
|---|---|---|---|---|
| Geographic (lon/lat) | 4326 (WGS84) | degrees | area, distance, shape all distort | data storage, global extent |
| Projected (Cartesian) | 32650 (UTM 50N) | metres | minimal within zone | local analysis, distance/area |

**Rule:** Never compute Euclidean distances on geographic (lon/lat) coordinates. Always reproject to a suitable projected CRS first.

### 1.2 Common CRS by Region and Purpose

| Purpose | Recommended CRS | EPSG | Notes |
|---|---|---|---|
| Worldwide web maps | Web Mercator | 3857 | Area/ distance strongly distorted — NOT for analysis |
| Global equal-area | Mollweide / Eckert IV | 54009 / 54012 | For area-based global analysis |
| Local analysis (UTM zone) | UTM {zone}{N/S} | 32601–32660 | 6° zones, < 1:1000 distortion within zone |
| Continental (Europe) | ETRS89-LAEA | 3035 | Equal-area, good for EU-wide analysis |
| Continental (USA) | NAD83 / Albers | 5070 | Equal-area conic for CONUS |
| China | CGCS2000 / Gauss-Kruger | 4490–4512 | China's official geodetic system; 3° or 1.5° zones |

### 1.3 CRS Pitfalls

- **On-the-fly reprojection masking:** QGIS/ArcGIS show data in project CRS regardless of layer CRS — the raw values are not transformed. When writing code, explicitly reproject.
- **Datum shifts:** WGS84 and CGCS2000 are nearly identical at most mapping scales, but NAD27 → WGS84 can shift ~10–100 m depending on location.
- **Latitude-dependent distortion:** Web Mercator doubles the displayed area of a Greenland pixel vs an equivalent pixel at the equator. Never compute density, distance, or area in 3857.
- **UTM zone boundaries:** A dataset straddling two UTM zones should be handled with an extended zone or Lambert conformal, not single UTM.
- **Vertical CRS:** Elevation values need a vertical datum (EGM96, EGM2008, NAVD88). Mixing vertical datums introduces systematic bias.

**Always ask:** "What CRS is this data in? If I compute distances, which CRS should I reproject to?"

---

## 2. Spatial Topology Fundamentals

### 2.1 Data Models

| Model | Examples | Best For |
|---|---|---|
| **Vector (discrete objects)** | Shapefile, GeoJSON, GeoPackage | Points, lines, polygons, boundaries |
| **Raster (continuous field)** | GeoTIFF, NetCDF, Zarr | Elevation, temperature, satellite imagery |
| **TIN** | Irregular triangulation | Surface modelling from point samples |

### 2.2 DE-9IM Spatial Predicates

The Dimensionally Extended Nine-Intersection Model defines how two geometries relate:

| Predicate | Meaning | SQL / GIS |
|---|---|---|
| **Equals** | Same geometry type, same coordinates | `ST_Equals` |
| **Disjoint** | No shared points | `ST_Disjoint` |
| **Intersects** | Any points in common (inverse of disjoint) | `ST_Intersects` |
| **Touches** | Boundaries touch, interiors don't intersect | `ST_Touches` |
| **Crosses** | Overlap at points (lines crossing) | `ST_Crosses` |
| **Within** | Wholly inside another geometry | `ST_Within` |
| **Contains** | Wholly contains another geometry | `ST_Contains` |
| **Overlaps** | Same dimension, interior overlaps partially | `ST_Overlaps` |

### 2.3 Spatial Autocorrelation (Tobler's First Law)

> "Everything is related to everything else, but near things are more related than distant things." — Waldo Tobler

- **Positive spatial autocorrelation:** nearby locations have similar values (clustering)
- **Negative autocorrelation:** nearby locations have dissimilar values (dispersion)
- **No autocorrelation:** spatial random pattern
- **Implied model assumption:** most geospatial ML models assume spatial autocorrelation exists; naive train/test splits (random, not spatially structured) leak information.

### 2.4 Spatial Weights Matrix

| Type | Description | When to Use |
|---|---|---|
| **Rook contiguity** | Shares edge | Regular grids, administrative polygons |
| **Queen contiguity** | Shares edge or vertex | More flexible connectivity |
| **k-Nearest Neighbours** | k closest centroids | Irregularly spaced point data |
| **Inverse distance** | $w_{ij} = 1 / d_{ij}^\alpha$ | Continuous distance decay |
| **Fixed distance band** | All neighbours within radius r | When process has a known interaction range |
| **Dual-power (bi-square)** | $w_{ij} = [1 - (d_{ij}/r)^2]^2$ for $d < r$, else 0 | Smoothly truncated kernel |

**Always normalise:** Row-standardise (each row sums to 1) before computing Moran's I or spatial lag.

### 2.5 Scale Effects

- **MAUP (Modifiable Areal Unit Problem):** The same point data aggregated to different zoning boundaries produces different statistical results. Always test sensitivity to aggregation scale.
- **Edge effects:** Observations near the study-area boundary have fewer neighbours, biasing local statistics. Use a buffer zone or edge-correction.
- **Zone effect:** Boundaries drawn differently (e.g. county vs watershed vs grid) change correlation results.

---

## 3. Earth System Science Processes

Earth's surface is a coupled system of interacting spheres. A geoscience analysis that treats one sphere in isolation will miss dominant drivers.

### 3.1 The Spheres

| Sphere | Key State Variables | Dominant Processes | Typical Data |
|---|---|---|---|
| **Atmosphere** | T, P, q, u, v, radiation | Circulation, convection, precipitation, boundary-layer turbulence | ERA5, GCM outputs, weather station records |
| **Hydrosphere** | discharge (Q), stage (H), soil moisture (θ), groundwater head | Runoff generation, infiltration, evapotranspiration, baseflow | Stream gauge, GRACE, satellite soil moisture |
| **Lithosphere** | elevation (z), slope, aspect, curvature, lithology, soil type | Weathering, erosion, tectonic uplift, isostasy, soil formation | DEM (SRTM, NASADEM), lithological maps, soil maps |
| **Biosphere** | LAI, NDVI, NPP, biomass, species richness | Photosynthesis, phenology, disturbance, succession | MODIS, Landsat, field plots, species occurrence |
| **Cryosphere** | glacier mass balance, sea-ice extent, permafrost ALT, SCA | Ablation, accumulation, freeze-thaw, calving | ICESat, GRACE, MODIS snow cover, permafrost maps |

### 3.2 Key Cross-Sphere Interactions

| Interaction | Example | Why It Matters |
|---|---|---|
| **Land-atmosphere** | Soil moisture affects PBL height → convective precipitation → changes soil moisture | Coupled feedback loops; uncoupled models mispredict |
| **Ocean-atmosphere** | ENSO → global T/P anomalies → agricultural yield | Teleconnections operate at planetary scale |
| **Cryosphere-hydrosphere** | Glacier melt → streamflow augmentation → sea-level rise | Multi-decadal lags confuse trend attribution |
| **Lithosphere-biosphere** | Topography → orographic precipitation → vegetation gradients | Covarying drivers; confounding in regression |
| **Geophysical-surface** | Neotectonics → drainage organisation → basin morphology | Long-term boundary condition for surface processes |

**When building a model or research question that touches more than one sphere, always acknowledge the coupling and state which feedbacks are included vs omitted.**

---

## 4. Spatial Analysis Techniques Catalogue

Below is an overview of core spatial analysis techniques. Detailed algorithmic descriptions, assumptions, and implementation notes are in `references/spatial-analysis-techniques.md` (Codex mirror; the main skill can reference this content inline).

### 4.1 Spatial Correlation

| Technique | What It Tests |
|---|---|
| **Global Moran's I** | Overall clustering/dispersion of a variable across the study area. Output: I ∈ [-1, 1], z-score, p-value |
| **Geary's C** | Similar to Moran's I but emphasises pairwise differences. C ∈ [0, 2]. |
| **Getis-Ord General G** | Detects high-value (hot) vs low-value (cold) concentration at global scale |
| **Anselin Local Moran's I (LISA)** | Per-location cluster type: HH, HL, LH, LL with significance |
| **Getis-Ord Gi*** | Per-location z-score: hot spots and cold spots (with multiple-testing correction) |

### 4.2 Geographically Weighted Regression

| Model | Description |
|---|---|
| **GWR** | $y_i = \beta_0(u_i,v_i) + \sum_k \beta_k(u_i,v_i) x_{ik} + \varepsilon_i$ — coefficients vary by location |
| **MGWR** | Each predictor has its own bandwidth — some processes operate globally, others locally |
| **GTWR** | Spatiotemporal extension: coefficients vary in both space and time |

**Key considerations:**
- Bandwidth selection: AICc, CV. Too-small bandwidth overfits; too-large miscues local variation.
- Kernel: Gaussian (continuous) vs bi-square (truncated). Adaptive kernel when data density varies.
- Local collinearity: test condition number at each location.

### 4.3 Spatial Pattern Analysis

| Technique | Question Answered |
|---|---|
| **Kernel Density Estimation (KDE)** | Where is the intensity of point events highest? |
| **Ripley's K / Besag's L** | At what distance scales does clustering occur vs CSR? |
| **Average Nearest Neighbour** | Are points more clustered or dispersed than random? |
| **Quadrat analysis / VMR** | Variance-to-mean ratio with chi-square significance |

### 4.4 Spatial Clustering

| Method | Characteristics |
|---|---|
| **k-means (spatially constrained)** | Partitions into k clusters; adjacency constraints prevent fragmented regions |
| **DBSCAN / HDBSCAN** | Density-based; finds clusters of arbitrary shape; handles noise |
| **SKATER** | Tree-based regionalisation; maximises internal homogeneity under spatial adjacency constraint |
| **Hierarchical (AGNES)** | Bottom-up merging with spatial linkage constraints |

### 4.5 Spatiotemporal Analysis

| Method | Description |
|---|---|
| **Space-time cube** | $x \times y \times t$ bins; each bin stores a summary statistic |
| **Emerging hot spot analysis** | Mann-Kendall trend on per-location Gi* z-scores → 17 categories (e.g. new, intensifying, persistent, oscillating) |
| **Mann-Kendall / Theil-Sen** | Monotonic trend test + slope estimation for spatial time series |
| **STL decomposition** | Seasonal-trend decomposition for spatiotemporal data |

### 4.6 Remote Sensing Deep Learning

| Architecture | Task | Typical Use |
|---|---|---|
| **U-Net** | Semantic segmentation | Land cover, water bodies, building footprints |
| **DeepLabV3+** | Semantic segmentation | Road extraction, crop type mapping |
| **ResNet / ResNeXt** | Scene classification | Land use classification |
| **Vision Transformer (ViT, Swin)** | Scene / object classification | When large labelled datasets exist |
| **Change detection (Siamese/UNet)** | Multi-temporal pixel change | Deforestation, urban expansion, disaster mapping |

**Spectral consideration:** Remote sensing models must account for sensor spectral response (different band configurations, bit depths, solar zenith angle correction, atmospheric correction).

---

## 5. Workflow Guidance

When applying this skill to a research problem, follow this sequence:

### Step 1: Problem Localisation
- Which earth-science subdomain? (hydrology vs climate vs geology vs ecology)
- Which sphere(s) are involved? Are cross-sphere interactions relevant?
- Is the problem fundamentally spatial (autocorrelation expected) or aspatial with spatial covariates?

### Step 2: Choose Appropriate CRS
- What CRS is the input data in?
- For distance operations → projected CRS (local UTM or Lambert)
- For area operations → equal-area projection (Albers, Mollweide, sinusoidal)
- For global data → geographic with great-circle distance, or project per region
- Declare the output CRS with EPSG code

### Step 3: Spatial Extent & Resolution
- What is the study area extent? Does it span UTM zones?
- What is the native resolution of the data? Is aggregation or interpolation justified?
- Is MAUP relevant? Test sensitivity to zoning.

### Step 4: Select Analytical Technique
- Correlation / clustering → ESDA (Moran's I, Gi*, LISA)
- Modelling non-stationary processes → GWR / MGWR / GTWR
- Point pattern → KDE, Ripley's K, ANN
- Clustering → SKATER for region-building, DBSCAN for density-based
- Change over time → emerging hot spot, Mann-Kendall, STL

### Step 5: Verify with QGIS (if available)
- Invoke `/qgis-mcp` to load data, run verification operations, and cross-check CRS alignment.
- Document any discrepancies between expected and actual QGIS results.

### Step 6: Cross-System Synthesis
- If multiple spheres are involved, discuss how interactions were (or were not) modelled.
- If feedback loops are omitted, state what bias this introduces.

---

## 6. QGIS Experiment Verification

When the research involves verifiable geospatial operations (buffer, spatial join, coordinate transformation, layer overlay, distance/area computation, map visualisation), ALWAYS check whether QGIS is available:

```bash
claude mcp list | grep qgis
```

If QGIS MCP is registered AND QGIS is running with the plugin server started:

1. **Invoke `/qgis-mcp`** with the task: load layers, run the spatial operation, compare results
2. **Verify CRS alignment** — check that all layers share a consistent CRS before joining/overlaying
3. **Document discrepancies** — if the QGIS result differs from your in-line reasoning, trust QGIS and report the difference

This transforms the LLM's internal spatial reasoning from speculative to grounded. The QGIS-MCP server is documented in `docs/integrations/qgis-mcp.md`; if it is not yet registered, see that doc for setup.

> A dedicated QGIS-MCP layer may be added to ARIS's `allowed-tools` in the future for tighter integration.

---

## 7. Output Contract

Every analysis or paper section produced while this skill is active must include, in the Methods section or equivalent:

1. **Study area:** spatial extent (bounding box or administrative boundary)
2. **CRS:** EPSG code for all input data and output products, with justification
3. **Projection rationale:** why this projection was chosen for the operation (equal-area for area metrics, conformal for shape analysis, equidistant for distance)
4. **Spatial weights scheme:** type, distance threshold / k, row-standardised? (if used)
5. **Scale sensitivity:** any MAUP, edge-effect, or zone-effect diagnostics run
6. **QGIS verification:** what was checked, discrepancies found (or "not available")

---

## 8. Key Rules

- **Never compute Euclidean distances on lon/lat coordinates.** Always reproject first.
- **Never assume data is in WGS84 (EPSG:4326).** Verify the actual CRS from metadata, or assume unknown and require user confirmation.
- **Never treat Web Mercator (EPSG:3857) as suitable for analysis.** It is for base maps only.
- **Always row-standardise spatial weights** before computing Moran's I or spatial lag.
- **Always declare CRS** in any output — a spatial product without a CRS is scientifically useless.
- **When in doubt about a spatial operation, check with QGIS via `/qgis-mcp`** instead of reasoning from mental model.
- **Cross-sphere processes cannot be reduced to single-sphere models** — state omitted feedbacks.
