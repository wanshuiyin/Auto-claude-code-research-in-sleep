# Spatial Analysis Techniques Reference

Detailed reference for spatial analysis methods used in geoscience research. Organised by technique category.

> **Source attribution:** This reference draws on the GIS spatial analysis course at [no-con.github.io/GIS_SA](https://no-con.github.io/GIS_SA/), covering its 14-chapter curriculum from spatial statistics through remote sensing deep learning.

---

## CRS Implications for Spatial Analysis

The choice of CRS affects every spatial analysis technique. Before applying any method below, verify CRS:

| Technique | CRS Requirement | Why |
|---|---|---|
| **Distance buffers** | Projected CRS required | Geographic degrees are not uniform distance |
| **GWR bandwidth** | Projected CRS required | Distance kernel is CRS-dependent; coefficients shift under reprojection |
| **Ripley's K** | Projected CRS required; consistent across comparisons | Distance-based; across-study comparison invalid if CRS differs |
| **Area-based metrics** | Equal-area projection required | Area distortion in conformal/conic projections is > 20% at high latitudes |
| **KDE** | Projected CRS for meaningful density | Density = count/area in map units |
| **Global correlation** | Projection should minimise distortion for study area | Large-extent studies may need per-zone analysis |
| **Spatial weights** | Distance weights computed in projected CRS | Inverse distance weight depends on distance metric |

**General rule:** If the method uses a distance, area, or density — the CRS must preserve that property. Geographic CRS (EPSG:4326) preserves neither: always reproject to an appropriate projected CRS.

---

## 1. Spatial Statistics Foundations

- **Descriptive statistics:** mean, median, mode, range, IQR, variance, standard deviation, skewness, kurtosis — computed spatially (zonal statistics) or globally
- **Inferential statistics:** normal distribution, 3-sigma principle, z-score standardisation
- **Global vs local statistics:** global statistics summarise the entire study area; local statistics (e.g. Local Moran's I) compute per-feature values
- **Null hypothesis in spatial statistics:** Complete Spatial Randomness (CSR) — events are independent and uniformly distributed. Rejecting CSR is the first step in most spatial analyses.

---

## 2. Exploratory Spatial Data Analysis (ESDA)

- **Visual tools:** histogram, box plot (with mild/extreme outlier detection via 1.5IQR / 3IQR), scatter plot, parallel coordinate plot, stem-and-leaf plot
- **Spatial visualisation:** thematic maps, choropleth maps, mapped box plots, Thiessen polygons (Voronoi diagrams)
- **Semivariogram / semivariance cloud:** measures spatial dependence as a function of distance; foundational for kriging
- **Trend analysis:** detects global first-order (deterministic) spatial trends
- **Spatial autocorrelation analysis:** Moran scatter plot (z vs spatial lag of z), LISA cluster map

---

## 3. Spatial Pattern Analysis

### Kernel Density Estimation (KDE)

$$\hat{f}(x) = \frac{1}{nh^2} \sum_{i=1}^n K\left(\frac{x - x_i}{h}\right)$$

- **Bandwidth selection (h):** Silverman's rule of thumb, cross-validation, or likelihood-based. Smaller h → undersmoothed (noisy), larger h → oversmoothed (blurred).
- **Kernel functions:** Gaussian, Epanechnikov (optimal MSE), quartic, triangular, uniform
- **Adaptive vs fixed bandwidth:** adaptive adjusts h to local data density — better for heterogeneous point patterns

### Ripley's K Function

$$K(d) = \frac{1}{\lambda} \sum_i \sum_{j\neq i} \frac{I(d_{ij} < d)}{w_{ij}}$$

- Multi-distance test of CSR. Besag's L: $L(d) = \sqrt{K(d)/\pi} - d$ — under CSR, L(d) = 0
- **Confidence envelopes:** Monte Carlo simulation of CSR, typically 99 iterations
- **Edge correction:** without it, points near the boundary have fewer neighbours, biasing K downward

### Average Nearest Neighbour

$$R = \frac{\bar{d}_{obs}}{\bar{d}_{exp}} \quad \text{where} \quad \bar{d}_{exp} = \frac{0.5}{\sqrt{n/A}}$$

- R < 1: clustered; R > 1: dispersed; R = 1: random
- Z-test under CSR null hypothesis

### Quadrat Analysis / Variance-Mean Ratio (VMR)

- Study area divided into quadrats; count events per quadrat
- VMR = variance / mean. VMR > 1: clustered; VMR < 1: regular
- Chi-square test against CSR

---

## 4. Spatial Correlation Analysis

### Spatial Weights Matrix Construction

Methods for defining $W$ (most critical step for correlation analysis):

- **Polygon contiguity:** Rook (edge), Queen (edge + vertex)
- **Distance-based:** inverse distance ($w_{ij} = 1/d_{ij}^\alpha$), fixed distance band, k-nearest neighbours
- **Spatiotemporal windows:** combine spatial and temporal distance thresholds
- **Row-standardisation:** $w_{ij} / \sum_j w_{ij}$ — ensures each observation has equal total weight

### Global Moran's I

$$I = \frac{n\sum_i\sum_j w_{ij}(x_i - \bar{x})(x_j - \bar{x})}{(\sum_i\sum_j w_{ij})\sum_i (x_i - \bar{x})^2}$$

- **Range:** approximately [-1, 1]. I > 0: positive autocorrelation (clustering); I < 0: negative (dispersion)
- **Inference:** z-test with expected value $E[I] = -1/(n-1)$; variance depends on the weights matrix structure
- **Interpretation caution:** Global Moran's I is a single summary — it cannot detect local variation or clusters

### Geary's C

$$C = \frac{(n-1)\sum_i\sum_j w_{ij}(x_i - x_j)^2}{2(\sum_i\sum_j w_{ij})\sum_i (x_i - \bar{x})^2}$$

- C ∈ [0, 2]; C = 1: no autocorrelation; C < 1: positive; C > 1: negative
- More sensitive to local differences than Moran's I

### Getis-Ord General G

- Detects concentration of high or low values
- Positive significant G: high-value clustering; negative significant G: low-value clustering
- Unlike Moran's I, G distinguishes hot vs cold clustering

### Anselin Local Moran's I (LISA)

$$I_i = \frac{(x_i - \bar{x})}{m_2} \sum_j w_{ij}(x_j - \bar{x})$$

- **Four cluster types:** HH (high-high), HL (high-low outlier), LH (low-high outlier), LL (low-low)
- **Significance:** pseudo p-value based on conditional permutation (typically 999 permutations, α = 0.05)
- **Multiple testing correction:** Bonferroni or FDR on local statistics

### Getis-Ord Gi\* (Hot Spot Analysis)

$$G_i^* = \frac{\sum_j w_{ij}x_j - \bar{X}\sum_j w_{ij}}{S\sqrt{[n\sum_j w_{ij}^2 - (\sum_j w_{ij})^2]/(n-1)}}$$

- Positive z-score: hot spot (high values cluster); negative: cold spot
- Includes the target feature itself ($w_{ii} \neq 0$) — distinguishes Gi\* from Gi
- **Multiple testing:** with thousands of features, use FDR correction at α = 0.05 or false discovery rate < 5%

---

## 5. Geographically Weighted Regression (GWR)

### Core GWR Model

$$y_i = \beta_0(u_i,v_i) + \sum_k \beta_k(u_i,v_i)x_{ik} + \varepsilon_i$$

### Kernel Functions for Spatial Weighting

| Kernel | Formula | Characteristics |
|---|---|---|
| **Gaussian** | $w_{ij} = \exp(-(d_{ij}/b)^2)$ | Continuous, all points have non-zero weight |
| **Bi-square (truncated)** | $w_{ij} = [1-(d_{ij}/b)^2]^2$ for $d_{ij} < b$, 0 otherwise | Zero outside bandwidth; computationally efficient |
| **Inverse distance** | $w_{ij} = 1/d_{ij}^\alpha$ | Heavy-tailed; sensitive to near-zero distances |

### Bandwidth Optimisation

- **Fixed bandwidth (distance):** constant kernel radius. Use when data density is uniform.
- **Adaptive bandwidth (k-NN):** radius varies to include k nearest neighbours. Use when data density varies (e.g. cities).
- **AICc (corrected AIC):** minimised to select bandwidth — trade-off between fit and degrees of freedom
- **Cross-validation (CV):** $\min \sum_i [y_i - \hat{y}_{\neq i}(b)]^2$

### GWR Extensions

| Model | Innovation | Use Case |
|---|---|---|
| **MGWR** (Multiscale) | Per-predictor bandwidths — some coefficients vary rapidly, others smoothly | When processes operate at different spatial scales |
| **GTWR** (Geographically and Temporally Weighted) | Spatial + temporal distance weighted jointly | Panel / time-series spatial data |
| **GNNWR** | Neural network replaces Gaussian kernel | Non-linear spatial weighting |

### Diagnostics

- **Local R²:** per-location goodness of fit — where does the model perform well/poorly?
- **Local condition number:** detect collinearity at each location (κ > 30 indicates local collinearity)
- **ANOVA:** compare GWR vs OLS — significant improvement justifies the added complexity?
- **Simpson's paradox:** global vs local relationships can have opposite signs. GWR reveals this; OLS hides it.

---

## 6. Spatial Clustering Analysis

### Partitioning Methods

| Method | Key Parameter | Characteristics |
|---|---|---|
| **k-means (spatially constrained)** | k clusters | Minimises within-cluster sum of squares; spatial adjacency constraints via contiguity matrix |
| **k-medoids (PAM)** | k clusters | Robust to outliers; uses actual data points as cluster centres |
| **ISODATA** | Thresholds (merge/split) | Adaptive k; merges small clusters, splits large diffuse ones |

### Density-Based Methods

| Method | Key Parameters | Characteristics |
|---|---|---|
| **DBSCAN** | eps (ε), minPts | Finds arbitrarily shaped clusters; labels noise points; ε selection via k-distance plot |
| **HDBSCAN** | min_cluster_size | Hierarchical variant; no ε parameter; variable density clusters |
| **OPTICS** | minPts | Produces reachability plot; visual cluster hierarchy |

### Spatial-Constrained Methods

| Method | Concept | Use Case |
|---|---|---|
| **SKATER** | Minimum spanning tree on adjacency graph, pruned to k regions | Regionalisation: contiguous, internally homogeneous regions |
| **Spatially constrained multivariate clustering** | Feature similarity + adjacency penalty combined | Multi-variable zone design |

### Clustering Validation

| Metric | What It Measures |
|---|---|
| **Silhouette score** | How similar a point is to its own cluster vs nearest neighbour; range [-1, 1] |
| **Gap statistic** | Within-cluster dispersion compared to null reference |
| **Elbow method (WCSS)** | Within-cluster sum of squares vs k; inflection point |
| **Davies-Bouldin index** | Average similarity between each cluster and its most similar one |

---

## 7. Spatiotemporal Analysis

### Space-Time Cube

- 3D structure: $x \times y \times t$ bins
- Each bin stores count, mean, or other summary statistic
- Visualised as 2D map with time slider, 3D voxel plot, or 2.5D time series

### Emerging Hot Spot Analysis

1. Compute Getis-Ord Gi\* per time step for each location
2. Apply Mann-Kendall trend test to the time series of z-scores
3. **17 output categories** including:
   - **New:** hot spot in most recent time step, never before
   - **Intensifying:** increasingly hot over time
   - **Persistent:** continuously hot for ≥ 90% of time steps
   - **Diminishing:** decreasing hotness over time
   - **Sporadic:** hot on and off
   - **Oscillating:** hot/cold alternating with periodic pattern
   - **Historical:** once hot, now not

### Mann-Kendall Trend Test

- Non-parametric test for monotonic trend
- S statistic based on pairwise comparisons; normal approximation for large n
- Theil-Sen slope: median of all pairwise slopes (robust to outliers)

---

## 8. Geospatial Big Data

### Distributed Spatial Indexing

| System | Cell Type | Best For |
|---|---|---|
| **Geohash** | Rectangular Z-order | Simple, widely supported |
| **H3** | Hexagonal | Uniform neighbour relationships, no edge distortion |
| **S2** | Hierarchical square | Google-level precision, multi-resolution |
| **QuadTree** | Adaptive square | Variable-resolution raster storage |

### Cloud Platforms

- **Google Earth Engine:** planetary-scale geospatial analysis; Python/JS API; Landsat/Sentinel/MODIS archives
- **STAC (SpatioTemporal Asset Catalog):** standardised metadata for raster assets; browse/search across cloud archives
- **PostGIS:** spatial extension for PostgreSQL; spatial indexing (GiST), spatial joins, SQL-based analysis

---

## 9. Remote Sensing Deep Learning

### Common Architectures

| Architecture | Key Innovation | Task |
|---|---|---|
| **U-Net** | Encoder-decoder with skip connections | Semantic segmentation at pixel level |
| **DeepLabV3+** | Atrous spatial pyramid pooling | Multi-scale context capturing for segmentation |
| **ResNet** | Residual connections (skip-layer) | Very deep networks without vanishing gradient |
| **Vision Transformer (ViT/Swin)** | Self-attention over image patches | Replaces convolution entirely; large data required |

### Training Considerations for Remote Sensing

- **Spectral bands:** satellite imagery often has > 3 bands. Pre-trained RGB ImageNet models need band adaptation (PCA, band selection, or first-layer fusion).
- **Data augmentation:** geometric (rotation, flip, scale) AND spectral (brightness, contrast, histogram matching)
- **Sensor-specific:** different sensors have different GSD, swath width, bit depth — model trained on Sentinel-2 (10–60 m) may not transfer to WorldView (0.3 m)
- **Cloud and shadow:** common in optical imagery; clouds need masking; shadows confuse classification
- **Temporal consistency:** for change detection, co-registration of multi-temporal imagery to sub-pixel accuracy

### Evaluation Metrics

| Metric | Formula | Use |
|---|---|---|
| **Overall accuracy** | (TP+TN)/N | Simple global metric |
| **Precision** | TP/(TP+FP) | False positive avoidance |
| **Recall / True Positive Rate** | TP/(TP+FN) | False negative avoidance |
| **F1 score** | 2 × P × R / (P + R) | Harmonic mean; balanced class metric |
| **Kappa coefficient** | (p_o - p_e)/(1 - p_e) | Agreement beyond chance |
| **Mean IoU (Jaccard)** | TP/(TP+FP+FN) | Standard segmentation metric |

---

## 10. Common Datasets

| Dataset | Type | Resolution | Access |
|---|---|---|---|
| **Sentinel-2** | Optical MSI (13 bands) | 10–60 m, 5-day revisit | Copernicus Open Access Hub |
| **Landsat 8/9** | Optical/TIR (11 bands) | 30 m (15 m pan), 16-day | USGS EarthExplorer |
| **MODIS** | Multi-spectral (36 bands) | 250–1000 m, daily | LP DAAC |
| **SRTM / NASADEM** | Digital elevation | 30 m (SRTM) / 12 m (NASADEM) | USGS EarthExplorer |
| **ERA5** | Reanalysis climate | ~31 km, hourly | Copernicus Climate Data Store |
| **GRACE** | Gravity / terrestrial water storage | ~300 km, monthly | NASA JPL |
| **OpenStreetMap** | Vector (roads, buildings, land use) | Varies | Geofabrik / Overpass API |
| **Natural Earth** | Vector (boundaries, coastlines) | 1:10m–1:110m | naturalearthdata.com |
