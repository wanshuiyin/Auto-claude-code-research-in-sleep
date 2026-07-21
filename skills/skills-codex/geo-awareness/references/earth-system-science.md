# Earth System Science Reference

Reference for Earth's spheres, their key processes, interactions, and typical data sources. Use when research involves cross-sphere interactions, multi-system coupling, or Earth-surface process modelling.

---

## 1. Atmosphere

### Key State Variables
- Temperature (T), pressure (P), specific humidity (q), wind (u, v), radiation fluxes (shortwave, longwave)

### Dominant Processes
- **Atmospheric circulation:** Hadley (tropics), Ferrel (mid-latitudes), Polar cells; driven by differential solar heating and Coriolis effect
- **ENSO (El Niño–Southern Oscillation):** SST anomalies in tropical Pacific → global teleconnections → precipitation/temperature anomalies worldwide
- **Precipitation formation:** convective (local, intense), stratiform (widespread, steady), orographic (terrain-lifted)
- **Greenhouse forcing:** CO₂, CH₄, H₂O absorb outgoing longwave radiation → surface warming
- **Planetary boundary layer:** lowest ~1 km; turbulent, directly coupled to surface fluxes (latent + sensible heat)

### Data Sources
- ERA5 (hourly, 31 km, global reanalysis)
- GCM outputs (CMIP6 for climate projections)
- Weather station records (GHCN, GSOD)
- TRMM/GPM (satellite precipitation)

### Common Analytical Questions
- Trend detection in temperature/precipitation (Mann-Kendall, Theil-Sen)
- Extreme event attribution (return period estimation)
- Downscaling GCM outputs to local scale (dynamical vs statistical)

---

## 2. Hydrosphere

### Key State Variables
- Streamflow discharge (Q), river stage (H), soil moisture (θ), groundwater head, evapotranspiration (ET)

### Dominant Processes
- **Water balance:** $P = ET + R + \Delta S$ (precipitation = evapotranspiration + runoff + storage change)
- **Runoff generation:** infiltration-excess (Hortonian), saturation-excess (Dunne), subsurface stormflow
- **Groundwater recharge:** precipitation percolation, focused recharge via ephemeral streams
- **Baseflow separation:** groundwater contribution to streamflow; recession curve analysis (Maillet, Brutsaert)
- **Urban hydrology:** increased impervious area → higher peak discharge, faster response, lower baseflow

### Data Sources
- Stream gauge records (USGS NWIS, GRDC)
- GRACE satellite (terrestrial water storage anomalies)
- Satellite soil moisture (SMAP, ESA CCI)
- MODIS ET product (MOD16)

### Common Analytical Questions
- Trend / change-point in streamflow regimes (Pettitt test, Mann-Kendall)
- Drought characterisation (SPI, SPEI, drought duration/severity)
- Flood frequency analysis (Gumbel, GEV, Log-Pearson III)
- Hydrological modelling (HBV, SWAT, PRMS) with spatial parameters

---

## 3. Lithosphere / Earth Surface Processes

### Key State Variables
- Elevation (z), slope, aspect, curvature, lithology, soil texture, regolith thickness

### Dominant Processes
- **Tectonic / structural:** fault activity, uplift/subsidence, basin morphology, lineament analysis
- **Fluvial:** erosion, sediment transport, channel geometry, terrace formation, alluvial fans
- **Aeolian:** dune morphology, loess deposition, dust transport
- **Glacial / periglacial:** glacial erosion, moraine formation, ice-wedge polygons, solifluction
- **Weathering:** physical (freeze-thaw, thermal), chemical (dissolution, hydrolysis), biological

### Soil Classification
- **USDA Soil Taxonomy:** 12 orders (Alfisols, Andisols, Aridisols, Entisols, Gelisols, Histosols, Inceptisols, Mollisols, Oxisols, Spodosols, Ultisols, Vertisols); texture triad (sand-silt-clay %)
- **WRB (World Reference Base):** 32 Reference Soil Groups

### Data Sources
- SRTM / NASADEM (30 m DEM)
- USGS 3DEP, ALOS World 3D
- SoilGrids250m (global soil properties)
- USGS lithological / geological maps

### Common Analytical Questions
- Drainage network extraction (flow accumulation, Strahler order)
- Landslide susceptibility mapping (DEM-based slope + lithology + triggering factors)
- Morphometric analysis (hypsometry, stream length-gradient index, relief ratio)

---

## 4. Biosphere

### Key State Variables
- Leaf Area Index (LAI), NDVI, Enhanced Vegetation Index (EVI), Gross Primary Production (GPP), Net Primary Production (NPP), biomass, species richness

### Dominant Processes
- **Photosynthesis:** conversion of solar energy to chemical energy; limited by light, water, nutrients, temperature
- **Carbon cycle:** NEP = GPP − Rₑ (net ecosystem production); forests are major carbon sinks
- **Phenology:** SOS (start of season) and EOS (end of season) timing; advancing in warming climates
- **Disturbance:** fire, logging, insect outbreaks, drought mortality — all alter vegetation structure and carbon balance
- **Land use/cover change:** deforestation, urbanisation, agricultural intensification, afforestation

### NPP Gradients
- **Latitudinal:** tropical forests (~1200 gC/m²/yr) → boreal forests (~400 gC/m²/yr) → tundra (~100 gC/m²/yr)
- **Elevational:** decreasing NPP with elevation (temperature limitation)

### Data Sources
- MODIS NDVI / EVI / LAI / GPP (MOD13, MOD15, MOD17)
- Landsat time series (30 m vegetation indices since 1984)
- ESA CCI Land Cover
- FLUXNET (eddy covariance tower observations)

### Common Analytical Questions
- Vegetation trend analysis (greening / browning via NDVI slope)
- Land cover classification / change detection (Landsat-based)
- Species distribution modelling (MaxEnt, random forest)
- Biomass estimation (allometric equations, LiDAR, SAR)

---

## 5. Cryosphere

### Key State Variables
- Glacier mass balance (specific mass balance in m w.e./yr), sea-ice extent / concentration / thickness, permafrost Active Layer Thickness (ALT), Snow Cover Area (SCA), Snow Water Equivalent (SWE)

### Dominant Processes
- **Glacier mass balance:** accumulation (snowfall) − ablation (melting + calving); Equilibrium Line Altitude (ELA) separates accumulation from ablation zones
- **Sea ice:** seasonal cycle (minimum in September, maximum in March for Arctic); declining trend driven by warming and feedback (albedo effect)
- **Permafrost:** ground that remains frozen ≥ 2 consecutive years; thaw releases CH₄ and CO₂; ALT increasing with warming
- **Snow:** SCA decreasing in Northern Hemisphere spring; SWE trends more complex (increasing in some cold regions, decreasing in temperate)

### Key Trends
- **Arctic sea ice:** September extent declining at ~13% per decade (satellite era, 1979–present)
- **Glacier mass loss:** global except for a few regions; Greenland and Antarctica dominate sea-level contribution
- **Permafrost warming:** observed at most monitoring sites; ALT increasing at ~1–2 cm/yr

### Data Sources
- ICESat / ICESat-2 (laser altimetry for ice thickness)
- GRACE / GRACE-FO (gravimetric ice mass change)
- MODIS snow cover (MOD10, MYD10)
- NSIDC sea-ice index
- Global Glacier Mass Balance (WGMS)

### Common Analytical Questions
- Glacier area / volume change over time (multi-temporal imagery)
- Snow cover trend analysis (MODIS time series)
- Permafrost degradation mapping (thermal remote sensing, InSAR)

---

## 6. Cross-System Interactions

### Land-Atmosphere Feedback

| Mechanism | Direction | Effect |
|---|---|---|
| **Soil moisture–precipitation** | SM ↑ → ET ↑ → PBL moistens → convection → P ↑ | Positive feedback (drought self-intensifying) |
| **Surface albedo–temperature** | Albedo ↑ (snow/ice) → net SW ↓ → cooling → snow persistence | Positive (albedo feedback) |
| **Vegetation–ET** | LAI ↑ → ET ↑ → surface cooling → more vegetation | Localised negative feedback |
| **Dust–radiation** | Dust ↑ → SW ↓ at surface → cooling; but heating in atmosphere | Complex; depends on dust properties |

### Ocean-Atmosphere Coupling

| Mode | Timescale | Global Impact |
|---|---|---|
| **ENSO** | 2–7 yr | Tropical P/T anomalies, mid-latitude teleconnections |
| **PDO (Pacific Decadal)** | 20–30 yr | Modulates ENSO impacts in North America |
| **AMO (Atlantic Multidecadal)** | 60–80 yr | Atlantic hurricane activity, Sahel rainfall, European climate |
| **IOD (Indian Ocean Dipole)** | 3–6 months | East Africa rainfall, Australian drought |

### Geophysical-Surface Coupling

| Process | Coupling | Observables |
|---|---|---|
| **Neotectonics** | Uplift → incision → drainage reorganisation | Knickpoints, river terraces, drainage asymmetry |
| **Volcanism** | Eruption → atmospheric aerosols → short-term cooling | Tephra layers, sulphate records |
| **Geothermal** | Heat flow → subglacial melt → ice dynamics | Basal sliding velocity, subglacial lakes |

**When research crosses spheres, the coupling mechanisms must be explicitly stated.** Omitting a known feedback while claiming the model captures the system response is a common flaw in earth-system ML papers.
