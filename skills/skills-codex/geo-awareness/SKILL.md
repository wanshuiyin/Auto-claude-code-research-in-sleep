---
name: geo-awareness
description: "Geoscience domain awareness — CRS, spatial topology, earth system science, core spatial analysis techniques (Moran's I, GWR, KDE, Ripley's K, LISA, spatiotemporal analysis, remote sensing DL). Use when the research touches earth science, geography, geology, hydrology, climatology, ecology, remote sensing, or any geospatial data, so the LLM applies correct spatial reasoning instead of naive generic-ML assumptions."
argument-hint: "[research-topic-or-question] [— sources: <source-list>]"
allowed-tools: Bash(*), Read, Write, Edit, Grep, Glob, WebSearch, WebFetch
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
| `/geo-mapping` | CRS selection, projection rationale, map layout conventions |

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
| Worldwide web maps | Web Mercator | 3857 | Area/distance strongly distorted — NOT for analysis |
| Global equal-area | Mollweide / Eckert IV | 54009 / 54012 | For area-based global analysis |
| Local analysis (UTM zone) | UTM {zone}{N/S} | 32601–32660 | 6° zones, < 1:1000 distortion within zone |
| Continental (Europe) | ETRS89-LAEA | 3035 | Equal-area, good for EU-wide analysis |
| Continental (USA) | NAD83 / Albers | 5070 | Equal-area conic for CONUS |
| China | CGCS2000 / Gauss-Kruger | 4490–4512 | China's official geodetic system; 3° or 1.5° zones |

### 1.3 CRS Pitfalls

- **On-the-fly reprojection masking:** Many GIS applications show data in project CRS regardless of layer CRS — the raw values are not transformed. When writing code, explicitly reproject.
- **Datum shifts:** WGS84 and CGCS2000 are nearly identical at most mapping scales, but NAD27 → WGS84 can shift ~10–100 m depending on location.
- **Latitude-dependent distortion:** Web Mercator doubles the displayed area of a Greenland pixel vs an equivalent pixel at the equator. Never compute density, distance, or area in 3857.
- **UTM zone boundaries:** A dataset straddling two UTM zones should be handled with an extended zone or Lambert conformal, not single UTM.
- **Vertical CRS:** Elevation values need a vertical datum (EGM96, EGM2008, NAVD88). Mixing vertical datums introduces systematic bias.

**Always ask:** "What CRS is this data in? If I compute distances, which CRS should I reproject to?"

## 2. Spatial Topology Fundamentals

### 2.1 Data Models

| Model | Examples | Best For |
|---|---|---|
| **Vector (discrete objects)** | Shapefile, GeoJSON, GeoPackage | Points, lines, polygons, boundaries |
| **Raster (continuous field)** | GeoTIFF, NetCDF, Zarr | Elevation, temperature, satellite imagery |
| **TIN** | Irregular triangulation | Surface modelling from point samples |

### 2.2 DE-9IM Spatial Predicates

| Predicate | Meaning | SQL / GIS |
|---|---|---|
| **Equals** | Same geometry type, same coordinates | `ST_Equals` |
| **Disjoint** | No shared points | `ST_Disjoint` |
| **Intersects** | Any points in common | `ST_Intersects` |
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
| **Dual-power (bi-square)** | Smoothly truncated kernel | Robust to outliers |

### 2.5 Scale Effects

- **MAUP (Modifiable Areal Unit Problem):** The same point data aggregated to different boundaries produces different results. Test sensitivity to aggregation scale.
- **Edge effects:** Observations near the boundary have fewer neighbours, biasing local statistics. Use a buffer zone or edge-correction.
- **Zone effect:** Boundaries drawn differently change correlation results.

## 3. Earth System Science Processes

### 3.1 The Spheres

| Sphere | Key State Variables | Dominant Processes | Typical Data |
|---|---|---|---|
| **Atmosphere** | T, P, q, u, v, radiation | Circulation, convection, precipitation, BL turbulence | ERA5, GCM outputs, weather stations |
| **Hydrosphere** | discharge (Q), stage (H), soil moisture (θ), groundwater head | Runoff, infiltration, ET, baseflow | Stream gauge, GRACE, satellite SM |
| **Lithosphere** | elevation (z), slope, aspect, lithology, soil type | Weathering, erosion, uplift, soil formation | DEM (SRTM, NASADEM), soil maps |
| **Biosphere** | LAI, NDVI, NPP, biomass, species richness | Photosynthesis, phenology, disturbance, succession | MODIS, Landsat, field plots |
| **Cryosphere** | glacier mass balance, sea-ice extent, permafrost ALT | Ablation, accumulation, freeze-thaw | ICESat, GRACE, MODIS snow |

### 3.2 Key Cross-Sphere Interactions

| Interaction | Example | Why It Matters |
|---|---|---|
| **Land-atmosphere** | Soil moisture → PBL → convection → precipitation feedback | Coupled feedback loops |
| **Ocean-atmosphere** | ENSO → global T/P anomalies | Teleconnections at planetary scale |
| **Cryosphere-hydrosphere** | Glacier melt → streamflow → sea-level rise | Multi-decadal lags |
| **Lithosphere-biosphere** | Topography → orographic precipitation → vegetation gradients | Covarying drivers in regression |
| **Geophysical-surface** | Neotectonics → drainage organisation → basin morphology | Long-term boundary conditions |

**When building a model touching more than one sphere, always acknowledge coupling and state included vs omitted feedbacks.**

## 4. Spatial Analysis Techniques Catalogue

### 4.1 Spatial Correlation

| Technique | What It Tests |
|---|---|
| **Global Moran's I** | Overall clustering/dispersion. I ∈ [-1, 1], z-score, p-value |
| **Geary's C** | Pairwise differences emphasis. C ∈ [0, 2] |
| **Getis-Ord General G** | High-value vs low-value concentration globally |
| **Anselin Local Moran's I (LISA)** | Per-location cluster type: HH, HL, LH, LL |
| **Getis-Ord Gi\*** | Per-location hot/cold spots with significance |

### 4.2 Geographically Weighted Regression

| Model | Description |
|---|---|
| **GWR** | Coefficients vary by location (location-specific slopes) |
| **MGWR** | Per-predictor bandwidths (mix of local and global processes) |
| **GTWR** | Spatiotemporal extension |

Key: bandwidth selection via AICc/CV, local collinearity check, adaptive vs fixed kernel.

### 4.3 Spatial Pattern Analysis

| Technique | Question Answered |
|---|---|
| **Kernel Density Estimation** | Where is point intensity highest? |
| **Ripley's K / Besag's L** | At what distances does clustering occur vs CSR? |
| **Average Nearest Neighbour** | Are points more clustered/dispersed than random? |
| **Quadrat analysis / VMR** | Variance-to-mean ratio significance |

### 4.4 Spatial Clustering

| Method | Characteristics |
|---|---|
| **Spatially constrained k-means** | Adjacency constraints prevent fragmented regions |
| **DBSCAN / HDBSCAN** | Density-based, arbitrary shapes, noise handling |
| **SKATER** | Tree-based regionalisation under adjacency constraint |
| **Hierarchical (AGNES)** | Bottom-up merging with linkage constraints |

### 4.5 Spatiotemporal Analysis

| Method | Description |
|---|---|
| **Space-time cube** | $x \times y \times t$ bins |
| **Emerging hot spot** | Mann-Kendall on per-location Gi\* z-scores → 17 categories |
| **Mann-Kendall / Theil-Sen** | Trend test + slope for spatial time series |
| **STL decomposition** | Seasonal-trend for spatiotemporal data |

### 4.6 Remote Sensing Deep Learning

| Architecture | Task | Typical Use |
|---|---|---|
| **U-Net** | Semantic segmentation | Land cover, water bodies |
| **DeepLabV3+** | Semantic segmentation | Road extraction, crop type |
| **ResNet / ResNeXt** | Scene classification | Land use classification |
| **Vision Transformer** | Scene / object classification | Large labelled datasets |
| **Siamese change detection** | Multi-temporal pixel change | Deforestation, urban expansion |

## 5. Workflow Guidance

### Step 1: Problem Localisation
- Which subdomain? Which sphere(s)? Cross-sphere interactions?
- Inherently spatial or aspatial with spatial covariates?

### Step 2: Choose Appropriate CRS
- Input data CRS? For distance → projected; for area → equal-area; for global → geographic + great-circle
- Declare output CRS with EPSG code

### Step 3: Spatial Extent & Resolution
- Study area extent? UTM zone boundaries? Native resolution?
- MAUP sensitivity test needed?

### Step 4: Select Analytical Technique
- Correlation → ESDA (Moran's I, Gi\*, LISA)
- Non-stationary modelling → GWR / MGWR
- Point pattern → KDE, Ripley's K
- Clustering → SKATER / DBSCAN
- Temporal change → emerging hot spot, Mann-Kendall

### Step 5: Cross-System Synthesis
- Multi-sphere interaction modelling; state omitted feedbacks.

## 6. Output Contract

Every analysis output must include:
1. **Study area extent** (bounding box or administrative boundary)
2. **CRS:** EPSG code for all data and outputs, with justification
3. **Projection rationale:** why chosen (equal-area, conformal, equidistant)
4. **Spatial weights scheme** (if used): type, threshold, row-standardised?
5. **Scale sensitivity:** MAUP / edge-effect diagnostics
6. **QGIS verification:** what was checked, discrepancies found

## 7. Key Rules

- **Never compute Euclidean distances on lon/lat coordinates.** Reproject first.
- **Never assume data is WGS84.** Verify actual CRS.
- **Never treat Web Mercator (EPSG:3857) as suitable for analysis.** Base maps only.
- **Always row-standardise spatial weights** before Moran's I or spatial lag.
- **Always declare CRS** in any output — spatial data without CRS is scientifically useless.
- **Cross-sphere processes cannot be reduced to single-sphere models** — state omitted feedbacks.
