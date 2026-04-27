# Prior Art Search Databases Guide

Use this reference in `/prior-art-search` for systematic patent and literature searching.

## When to Read

- Read when conducting prior art searches
- Read when formulating search queries for patents
- Read when classifying search results by IPC/CPC codes

## Patent Databases (Free, Web-Accessible)

### Google Patents
- **URL**: patents.google.com
- **Coverage**: US, EP, CN, WIPO, JP, KR, and 100+ jurisdictions
- **Search syntax**: Full-text search, inventor:, assignee:, CPC:, before:, after:
- **Strengths**: Best free full-text search, automatic translation of CN/JP/KR patents, family grouping
- **Weaknesses**: No legal status data, may lag behind official databases by weeks
- **Usage in skills**: `WebSearch "site:patents.google.com [keywords]"` or `WebFetch` for specific patent pages

### Espacenet (EPO)
- **URL**: worldwide.espacenet.com
- **Coverage**: 150+ million patent documents from 100+ authorities
- **Search syntax**: Classification=(CPC/IPC), Applicant=, Title/Abstract/Claims full text
- **Strengths**: Most comprehensive free database, machine translation, legal status via INPADOC
- **Weaknesses**: Interface is less intuitive, some features require registration
- **Usage**: `WebFetch` for search results and individual patent pages

### CNIPA Patent Search (中国及多国专利审查信息查询)
- **URL**: pss-system.cponline.cnipa.gov.cn (or similar)
- **Coverage**: Chinese patents (CN), the authoritative source for CN applications
- **Strengths**: Official Chinese patent data, full Chinese text, examination status
- **Weaknesses**: Interface in Chinese only, limited foreign coverage
- **Usage**: `WebFetch` for Chinese-specific searches

### USPTO Patent Full-Text Databases
- **PatFT**: patents.google.com/patents (US granted patents)
- **AppFT**: patents.google.com (US published applications)
- **PAIR**: patentcenter.uspto.gov (prosecution history)
- **Coverage**: US patents and applications
- **Usage**: `WebFetch` for specific US patent numbers

### WIPO PATENTSCOPE
- **URL**: patentscope.wipo.int
- **Coverage**: PCT international applications (WO publications)
- **Strengths**: Full PCT application texts, CLIR cross-lingual search
- **Usage**: `WebFetch` for PCT applications

## Academic Literature Databases

These are also prior art (non-patent literature, NPL):

| Database | URL | Coverage | API Available |
|----------|-----|----------|---------------|
| Google Scholar | scholar.google.com | Broadest academic coverage | No API, use WebSearch |
| Semantic Scholar | semanticscholar.org | CS, biomedical, 200M+ papers | Yes (SEMANTIC_SCHOLAR_API_KEY) |
| arXiv | arxiv.org | Preprints (CS, physics, math, etc.) | Yes (arxiv_fetch.py) |
| DBLP | dblp.org | CS bibliography | Yes (XML API) |
| CrossRef | crossref.org | DOIs for all published works | Yes (free, no key needed) |
| OpenAlex | openalex.org | 250M+ scholarly works | Yes (free, no key needed) |

## IPC/CPC Classification System

The International Patent Classification (IPC) and Cooperative Patent Classification (CPC) organize patents hierarchically:

### Structure
```
A 61 K  39 / 395
│  │  │  │   │
│  │  │  │   └─ Subgroup (specific)
│  │  │  └─ Group
│  │  └─ Subclass
│  └─ Class
└─ Section (A=Human necessities, B=Performing operations, C=Chemistry, etc.)
```

### Most Relevant Sections for Software/ML Inventions
- **G06F**: Electric digital data processing
- **G06N**: Computing arrangements based on specific computational models (AI/ML)
- **G06K**: Recognition of data; Presentation of data
- **G06T**: Image data processing or generation
- **G06Q**: Data processing systems for business/finance/administration
- **H04L**: Transmission of digital information (networking)
- **H04N**: Pictorial communication (video, image)

### Search Strategy with Classifications

1. Identify relevant IPC/CPC classes from the invention description
2. Search within those classes for targeted results
3. Expand to parent/child classes for broader coverage
4. Combine class-restricted searches with keyword searches

## Search Strategy Template

For each invention, execute this search protocol:

### Step 1: Keyword Search
```
Primary: [core inventive concept keywords]
Secondary: [technical problem keywords]
Tertiary: [advantage/feature keywords]
```

### Step 2: Classification Search
```
IPC/CPC: [identified classes]
Cross-reference: [related classes]
```

### Step 3: Assignee/Inventor Search
```
Key assignees: [known companies/universities in the field]
Key inventors: [known researchers in the field]
```

### Step 4: Citation Analysis
- Forward citations: who cited the closest prior art?
- Backward citations: what did the closest prior art cite?

### Step 5: Family Analysis
- Group results by patent family (same invention, different jurisdictions)
- Only the most relevant family member needs detailed analysis

## Output Format

For each prior art reference found:

```markdown
| Field | Content |
|-------|---------|
| Reference ID | [Patent number or paper DOI] |
| Type | Patent / Paper / Other |
| Title | [Full title] |
| Date | [Publication/priority date] |
| Assignee/Authors | [Who] |
| IPC/CPC | [Classification codes] |
| Key Teaching | [What does it teach, 2-3 sentences] |
| Relevant Claims | [Which claims, if patent] |
| Overlap Risk | HIGH / MEDIUM / LOW |
| Relationship | [Anticipating / Relevant / Background] |
```
