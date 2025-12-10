# 🧬 Ontology Viewer & Graph Explorer (Streamlit)

An interactive **Streamlit-based ontology workbench** for exploring OWL/RDF/Turtle ontologies through:

* Class and property browsing
* Interactive hierarchy and property-centric graphs
* Live SPARQL querying
* JSON export of graph neighbourhoods
* GitHub-hosted ontologies or uploaded local files

This tool was designed to support deep ontology inspection, testing, and collaboration workflows.

---

## ✨ Key Features

### ✅ Ontology Sources

* **GitHub mode**
  Load live ontologies directly from a GitHub repository (e.g. `/ontology/*.ttl`)
* **Upload mode**
  Upload and explore:

  * `.ttl` (Turtle)
  * `.owl`, `.rdf`, `.xml` (RDF/XML)

---

### ✅ Class Explorer

* Full searchable table of:

  * Class label
  * IRI
  * Parent class (`rdfs:subClassOf`)
  * Description (`rdfs:comment`)
* Live filtering by label or IRI
* Designed for fast ontology auditing

---

### ✅ Property Explorer (Robust)

* Detects:

  * `owl:ObjectProperty`
  * `owl:DatatypeProperty`
  * `owl:AnnotationProperty`
  * `rdf:Property`
  * Untyped properties inferred via `rdfs:domain` / `rdfs:range`
* Includes:

  * Property label
  * IRI
  * Kind (Object / Datatype / Annotation / Generic / Unknown)
  * Domain
  * Range
  * Description
* Filter by property type and text search

---

### ✅ Interactive Graph Views

#### 1) **Class Hierarchy Graph**

* Visualizes:

  * Focus class
  * Ancestors (parents)
  * Descendants (children)
* Colored roles:

  * 🟡 Focus
  * 🔵 Ancestors
  * 🟢 Descendants
  * ⚪ Others
* Right-side **details panel** shows:

  * Label, IRI, role
  * Definition
  * Types
  * Parents & children
  * Properties using the class as domain/range

#### 2) **Property-Centric Graph**

* Visualizes:

  * Property node (🟧)
  * Domain classes (🟪)
  * Range classes (🟦)
* Right-side property details:

  * Kind
  * Domain
  * Range
  * Description

---

### ✅ Graph Export

* Download the **current graph neighbourhood as JSON**
* Works for:

  * Class hierarchy graphs
  * Property-centric graphs
* Useful for:

  * Neo4j import
  * D3 / front-end visualization
  * Documentation snapshots

---

### ✅ SPARQL Playground

* Run arbitrary SPARQL queries against the loaded ontology
* Built-in presets, including:

  * List all classes
  * List all properties with domain/range
  * All subclasses of `EscapementMethod`
  * MU → CU → Stock chains (DFO model)
* Outputs live, sortable result tables

---

## 🛠️ Installation

### 1. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate    # Linux/macOS
venv\Scripts\activate       # Windows
```

### 2. Install dependencies

```bash
pip install streamlit rdflib requests pandas networkx pyvis
```

---

## ▶️ Running the App

### Local Machine

```bash
streamlit run app.py
```

### Remote Machine / VPN

```bash
streamlit run app.py --server.address 0.0.0.0 --server.port 8502
```

Then access from your browser:

```text
http://<REMOTE-IP>:8502
```

If the server uses `ufw`:

```bash
sudo ufw allow 8502
```

---

## 🔄 Ontology Source Modes

### ✅ GitHub Mode

* Loads `.ttl` files from:

```
/ontology/*.ttl
```

on a live GitHub repo.

* Supports:

  * Branch switching
  * Cache refresh
* Automatically reflects upstream ontology updates.

### ✅ Upload Mode

* Upload:

  * `.ttl` → Turtle
  * `.owl`, `.rdf`, `.xml` → RDF/XML
* Optional manual format override.
* Entire app switches instantly to the uploaded ontology.

---

## 🧭 Using the Graph Views

### Class Hierarchy Mode

1. Select a class.
2. Adjust depth slider.
3. View ancestors & descendants.
4. Inspect any node in the right-hand details panel.
5. Download the neighbourhood as JSON.

### Property-Centric Mode

1. Select a property.
2. View:

   * Domain classes
   * Range classes
3. Inspect property definition.
4. Download the property graph as JSON.

---

## 📤 Exporting Graph Data

Each graph mode includes:

```text
Download neighbourhood as JSON
```

Result format:

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

Compatible with:

* Neo4j loaders
* D3.js
* Cytoscape
* Custom front-end tools

---

## 🔎 Using This With Other Ontologies

This tool works with **any OWL/RDF ontology**, not just one project.

### ✅ Supported Formats

* Turtle (`.ttl`)
* RDF/XML (`.owl`, `.rdf`, `.xml`)

### ✅ Works Best When Ontology Has:

* `rdfs:label` for human-friendly class/property names
* `rdfs:comment` for definitions
* `rdfs:subClassOf` for hierarchy
* `rdfs:domain` / `rdfs:range` for properties

### ⚠️ Notes on Imports

* Imported ontologies (`owl:imports`) are **not automatically fetched**
* If your ontology references:

  * SKOS
  * RO
  * PROV
  * SOSA/SSN
    you may only see locally defined terms unless those imports are merged into your file.

### ✅ Best Practices for External Projects

If you plan to use this with other ontologies:

* ✅ Prefer a **single merged TTL** when possible
* ✅ Ensure properties have domain/range
* ✅ Declare property types (`owl:ObjectProperty`, etc.)
* ✅ Add labels for all public classes and properties

---

## 🧪 Example Use Cases

* Ontology QA/QC
* Schema refactoring
* Cross-standard alignment reviews
* Teaching ontology structure
* Neo4j/KG import validation
* DFO / PSC / research model exploration

---

## 🚀 Roadmap Ideas (Optional)

* Click-to-select nodes directly from the graph
* TTL / JSON-LD neighbourhood export
* Ontology diff between GitHub branches
* Class-to-property combined graphs
* Automated documentation generation
