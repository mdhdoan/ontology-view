# 📘 Project Abstract

**Ontology Viewer & Graph Explorer** is an interactive Streamlit-based workbench for exploring OWL/RDF/Turtle ontologies through structured tables, interactive graphs, and live SPARQL querying. The tool supports both GitHub-hosted ontologies and locally uploaded files, allowing rapid inspection, validation, and visualization of class hierarchies and property relationships.

Designed for technical users working with knowledge graphs, semantic data models, and research ontologies, the application enables:

* Fast auditing of class and property structures
* Visual exploration of subclass hierarchies and domain–range relationships
* Export of selected ontology neighbourhoods for downstream graph tools
* Live querying for schema verification and model exploration

The system is ontology-agnostic and can be applied to environmental science models, biomedical ontologies, enterprise knowledge graphs, and data integration projects requiring transparent schema validation.

---

# 🧑‍💻 Developer README — Ontology Viewer & Graph Explorer

This document describes the **internal architecture**, **data flow**, and **extension points** for developers working on the ontology viewer.

---

## 1. High-Level Architecture

```text
Streamlit UI
   |
   v
Ontology Loader
(GitHub / Upload)
   |
   v
rdflib.Graph  <---- SPARQL Engine
   |
   +--> Class Table
   +--> Property Table
   +--> Class Hierarchy Graph (networkx + pyvis)
   +--> Property-Centric Graph (networkx + pyvis)
   +--> JSON Export
```

### Core Technologies

* **Streamlit** – UI and app state
* **rdflib** – RDF parsing and SPARQL execution
* **pandas** – Tabular views
* **networkx** – Graph construction
* **pyvis (vis.js)** – Interactive graph rendering

---

## 2. Ontology Loading Pipeline

### 2.1 GitHub Loader

```python
def list_ttl_files(branch)
def load_graph_from_github(path, branch)
```

Flow:

1. Query GitHub API for `/ontology/*.ttl`
2. User selects a file
3. Raw file fetched via `raw.githubusercontent.com`
4. Parsed into `rdflib.Graph`

Caching:

* `@st.cache_data` used on GitHub calls to reduce API traffic

---

### 2.2 Upload Loader

```python
def load_graph_from_upload(uploaded_file, fmt=None)
```

Supported formats:

* `.ttl` → Turtle
* `.owl`, `.rdf`, `.xml` → RDF/XML

The loader:

1. Reads file bytes
2. Detects or forces format
3. Parses directly into `rdflib.Graph`
4. Replaces the active ontology in memory

---

## 3. Core Data Extractors

### 3.1 Class Extraction

```python
def extract_classes(graph)
```

Identifies:

* `owl:Class`
* `rdfs:Class`

Extracted fields:

* Label (`rdfs:label`)
* IRI
* Parent (`rdfs:subClassOf`)
* Definition (`rdfs:comment`)

Returns:

```text
DataFrame: [Label, IRI, SubClassOf, Comment]
```

---

### 3.2 Property Extraction (Robust Mode)

```python
def extract_properties(graph)
```

Detects:

* `owl:ObjectProperty`
* `owl:DatatypeProperty`
* `owl:AnnotationProperty`
* `rdf:Property`
* Untyped properties inferred from:

  * `rdfs:domain`
  * `rdfs:range`

Inferred property kinds:

* Object
* Datatype
* Annotation
* Generic
* Unknown

Returns:

```text
DataFrame: [Label, IRI, Kind, Domain, Range, Comment]
```

---

## 4. Graph Construction

### 4.1 Class Hierarchy Graph

```python
def build_class_subclass_graph(graph, focus_uri, max_depth)
```

Builds a `networkx.DiGraph` with:

* Focus class
* Ancestors (`rdfs:subClassOf*`)
* Descendants

Node attributes:

* `label`
* `role`: focus | ancestor | descendant | other

---

### 4.2 Property-Centric Graph

```python
def build_property_graph(graph, prop_uri)
```

Builds a graph around:

* Property node
* Domain classes
* Range classes

Node roles:

* property
* domain
* range

---

### 4.3 Graph Rendering

```python
def render_graph_pyvis(G)
```

* Converts NetworkX → PyVis
* Colors nodes based on role
* Outputs standalone HTML
* Embedded into Streamlit via:

```python
components.html(html, height=600)
```

---

## 5. Node Inspection Engine

```python
def describe_node(graph, iri_str)
```

Returns:

* Label
* IRI
* Comment
* rdf:type
* Parents
* Children
* Properties where used as domain
* Properties where used as range

Displayed in the right-hand inspection panel in Graph mode.

---

## 6. Graph Export System

```python
def graph_to_json_dict(G)
```

Exports:

```json
{
  "nodes": [
    {"id": "...", "label": "...", "role": "..."}
  ],
  "edges": [
    {"source": "...", "target": "...", "relation": "..."}
  ]
}
```

Download handled via:

```python
st.download_button(...)
```

---

## 7. SPARQL Engine

```python
def run_sparql(graph, query)
```

* Executes directly against in-memory `rdflib.Graph`
* Results converted to `pandas.DataFrame`
* Displayed using `st.dataframe`

### Built-in Query Presets

* All classes
* All properties with domain & range
* Escapement method hierarchy
* MU → CU → Stock membership chain

---

## 8. State Management Philosophy

Current design intentionally avoids:

* Cross-tab reactive state coupling
* Global `session_state` navigation control

Reason:

* Prevents accidental tab resets
* Keeps graph exploration deterministic
* Reduces Streamlit re-run instability

Each tab:

* Manages only its **local controls**
* Shares only **read-only ontology data**

---

## 9. Key Extension Points

Developers can add:

### ✅ New Graph Types

* Class ⇄ Property combined graphs
* Restriction-based graphs (`owl:Restriction`)
* Instance-level graphs (ABox)

### ✅ New Export Formats

* JSON-LD
* TTL neighbourhood export
* Cypher for Neo4j

### ✅ Ontology Diffing

* GitHub branch comparison
* Class/property change tracking

### ✅ Import Resolution

* Auto-fetch `owl:imports`
* Merge dependent ontologies into a single in-memory graph

---

## 10. Design Constraints & Tradeoffs

| Decision                         | Reason                          |
| -------------------------------- | ------------------------------- |
| No automatic owl:imports loading | Prevents uncontrolled expansion |
| Graph focused on schema (TBox)   | Keeps visualization readable    |
| JSON export over TTL export      | Tool-agnostic downstream use    |
| PyVis instead of D3              | Faster dev, stable interaction  |

---

## 11. Performance Notes

* Large ontologies (50k+ triples):

  * Class tables remain fast
  * Graph rendering should stay under ~500 nodes for usability
* Use:

  * Shallow `max_depth` for class graphs
  * Property-centric mode for dense graphs
