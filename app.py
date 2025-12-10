import requests
import streamlit as st
import pandas as pd
from rdflib import Graph, RDF, RDFS, OWL, Namespace

import networkx as nx
from pyvis.network import Network
import streamlit.components.v1 as components

from rdflib import URIRef
from rdflib.namespace import RDF

import json

# -------------------------------------------------------------------
# Config: repo details
# -------------------------------------------------------------------

OWNER = "dfo-pacific-science"
REPO = "dfo-salmon-ontology"
DEFAULT_BRANCH = "main"

ONTOLOGY_DIR = "ontology"

GITHUB_API_BASE = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{ONTOLOGY_DIR}"
GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{OWNER}/{REPO}"

# You can tweak these if you add more dirs later
TTL_SEARCH_PATHS = [
    "",            # repo root
    "ontology",    # ontology directory (future/now)
]


# -------------------------------------------------------------------
# Helpers: GitHub + RDF
# -------------------------------------------------------------------

def graph_to_json_dict(G: nx.DiGraph):
    """
    Convert a NetworkX DiGraph into a JSON-serializable dict
    with nodes and edges.
    """
    return {
        "nodes": [
            {
                "id": node,
                "label": data.get("label"),
                "role": data.get("role"),
            }
            for node, data in G.nodes(data=True)
        ],
        "edges": [
            {
                "source": src,
                "target": dst,
                "relation": data.get("relation", ""),
            }
            for src, dst, data in G.edges(data=True)
        ],
    }

def build_property_graph(graph: Graph, prop_uri):
    """
    Build a small graph centered on a property:
      - property node
      - domain class nodes
      - range class nodes
    Node roles:
      - 'property'
      - 'domain'
      - 'range'
    """
    G = nx.DiGraph()

    prop_str = str(prop_uri)
    prop_label = get_label(graph, prop_uri)

    G.add_node(prop_str, label=prop_label, role="property")

    # Domains: class -> property
    for d in graph.objects(prop_uri, RDFS.domain):
        d_str = str(d)
        d_label = get_label(graph, d)
        G.add_node(d_str, label=d_label, role="domain")
        G.add_edge(d_str, prop_str, relation="domainOf")

    # Ranges: property -> class
    for r in graph.objects(prop_uri, RDFS.range):
        r_str = str(r)
        r_label = get_label(graph, r)
        G.add_node(r_str, label=r_label, role="range")
        G.add_edge(prop_str, r_str, relation="rangeOf")

    return G


def _property_row(graph: Graph, p, kind: str):
    label = get_label(graph, p)
    comment = get_comment(graph, p)
    domains = [get_label(graph, d) for d in graph.objects(p, RDFS.domain)]
    ranges = [get_label(graph, r) for r in graph.objects(p, RDFS.range)]
    return {
        "Label": label,
        "IRI": str(p),
        "Kind": kind,
        "Domain": ", ".join(domains),
        "Range": ", ".join(ranges),
        "Comment": comment,
    }


def extract_properties(graph: Graph):
    """
    Return DataFrame of properties, trying to be robust to:
    - owl:ObjectProperty
    - owl:DatatypeProperty
    - owl:AnnotationProperty
    - rdf:Property
    - Untyped properties that have rdfs:domain or rdfs:range

    The DataFrame has a 'Kind' column indicating the inferred type.
    """
    props = set()

    # Explicit types
    for p in graph.subjects(RDF.type, OWL.ObjectProperty):
        props.add(p)
    for p in graph.subjects(RDF.type, OWL.DatatypeProperty):
        props.add(p)
    for p in graph.subjects(RDF.type, OWL.AnnotationProperty):
        props.add(p)
    for p in graph.subjects(RDF.type, RDF.Property):
        props.add(p)

    # Also anything with a domain or range
    for p in graph.subjects(RDFS.domain, None):
        props.add(p)
    for p in graph.subjects(RDFS.range, None):
        props.add(p)

    rows = []
    for p in props:
        types = set(graph.objects(p, RDF.type))

        if OWL.ObjectProperty in types:
            kind = "Object"
        elif OWL.DatatypeProperty in types:
            kind = "Datatype"
        elif OWL.AnnotationProperty in types:
            kind = "Annotation"
        elif RDF.Property in types:
            kind = "Generic"
        else:
            # Untyped, but used in domain/range
            kind = "Unknown"

        rows.append(_property_row(graph, p, kind=kind))

    if not rows:
        return pd.DataFrame(columns=["Label", "IRI", "Kind", "Domain", "Range", "Comment"])

    df = pd.DataFrame(rows).sort_values(["Kind", "Label"])
    return df.reset_index(drop=True)

def describe_node(graph: Graph, iri_str: str):
    """
    Return a dict of details for a given node IRI string:
    label, comment, types, parents, children, properties (domain/range).
    """
    uri = URIRef(iri_str)

    label = get_label(graph, uri)
    comment = get_comment(graph, uri)

    types = [str(t) for t in graph.objects(uri, RDF.type)]

    parents = [
        f"{get_label(graph, p)} ({p})"
        for p in graph.objects(uri, RDFS.subClassOf)
    ]

    children = [
        f"{get_label(graph, c)} ({c})"
        for c in graph.subjects(RDFS.subClassOf, uri)
    ]

    # Properties where this node is domain or range
    props_as_domain = [
        f"{get_label(graph, p)} ({p})"
        for p in graph.subjects(RDFS.domain, uri)
    ]
    props_as_range = [
        f"{get_label(graph, p)} ({p})"
        for p in graph.subjects(RDFS.range, uri)
    ]

    return {
        "label": label,
        "iri": iri_str,
        "comment": comment,
        "types": types,
        "parents": parents,
        "children": children,
        "props_as_domain": props_as_domain,
        "props_as_range": props_as_range,
    }

def build_class_subclass_graph(graph: Graph, focus_uri, max_depth: int = 2):
    """
    Build a networkx DiGraph of rdfs:subClassOf relationships
    around the focus_uri up to max_depth.

    Node attributes:
      - label: human-friendly label
      - role: 'focus' | 'ancestor' | 'descendant' | 'other'
    """
    G = nx.DiGraph()
    visited = set()
    roles = {}  # iri_str -> role

    def set_role(iri_str, new_role):
        """Keep 'focus' if already; otherwise allow ancestor/descendant."""
        old = roles.get(iri_str)
        if old == "focus":
            return
        if old is None:
            roles[iri_str] = new_role
        else:
            # if something is both ancestor/descendant, you could mark 'other'
            # but ancestor/descendant overlap is rare in clean hierarchies
            roles[iri_str] = old

    def add_neighbourhood(uri, depth_left, origin_role=None):
        if depth_left < 0:
            return

        uri_str = str(uri)
        if uri_str in visited:
            return
        visited.add(uri_str)

        label = get_label(graph, uri)
        G.add_node(uri_str, label=label)

        # Parents: uri rdfs:subClassOf parent
        for parent in graph.objects(uri, RDFS.subClassOf):
            parent_str = str(parent)
            parent_label = get_label(graph, parent)
            G.add_node(parent_str, label=parent_label)
            G.add_edge(parent_str, uri_str, relation="subClassOf")
            set_role(parent_str, "ancestor")
            add_neighbourhood(parent, depth_left - 1, origin_role="ancestor")

        # Children: child rdfs:subClassOf uri
        for child in graph.subjects(RDFS.subClassOf, uri):
            child_str = str(child)
            child_label = get_label(graph, child)
            G.add_node(child_str, label=child_label)
            G.add_edge(uri_str, child_str, relation="subClassOf")
            set_role(child_str, "descendant")
            add_neighbourhood(child, depth_left - 1, origin_role="descendant")

    # Focus node role
    focus_str = str(focus_uri)
    set_role(focus_str, "focus")

    # Build neighbourhood
    add_neighbourhood(focus_uri, max_depth)

    # Attach role attributes to nodes (default to 'other')
    for node in G.nodes:
        role = roles.get(node, "other")
        G.nodes[node]["role"] = role

    return G


def render_graph_pyvis(G: nx.DiGraph, height: str = "600px"):
    """
    Render a networkx graph using pyvis and return HTML
    that can be embedded in Streamlit.
    Colors nodes based on their 'role' attribute.
    """
    net = Network(height=height, width="100%", directed=True, notebook=False)

    # Simple color map for roles
    role_colors = {
        "focus": "#ffcc00",       # bright yellow
        "ancestor": "#1f77b4",    # blue
        "descendant": "#2ca02c",  # green
        "property": "#ff7f0e",    # orange
        "domain": "#9467bd",      # purple
        "range": "#17becf",       # teal
        "other": "#aaaaaa",       # grey
    }


    # Add nodes
    for node, data in G.nodes(data=True):
        label = data.get("label", node)
        role = data.get("role", "other")
        color = role_colors.get(role, "#aaaaaa")

        # Tooltip shows role + full IRI
        title = f"{label}<br><b>Role:</b> {role}<br><b>IRI:</b> {node}"

        net.add_node(
            node,
            label=label,
            title=title,
            color=color,
        )

    # Add edges
    for src, dst, data in G.edges(data=True):
        rel = data.get("relation", "subClassOf")
        net.add_edge(src, dst, title=rel)

    # Use pyvis defaults (no custom JSON options to avoid parsing issues)
    net.write_html("graph.html", open_browser=False)
    with open("graph.html", "r", encoding="utf-8") as f:
        html = f.read()
    return html


@st.cache_data(show_spinner=False)
def list_ttl_files(branch: str = DEFAULT_BRANCH):
    """Return list of (path, name) for all .ttl files in /ontology."""
    url = f"{GITHUB_API_BASE}?ref={branch}"
    resp = requests.get(url)

    if resp.status_code != 200:
        return []

    ttl_files = []
    for item in resp.json():
        if item["type"] == "file" and item["name"].endswith(".ttl"):
            ttl_files.append({
                "name": item["name"],
                "path": item["path"],   # e.g. "ontology/dfo-salmon.ttl"
            })

    return sorted(ttl_files, key=lambda x: x["name"])


@st.cache_data(show_spinner=True)
def load_graph_from_github(path: str, branch: str = DEFAULT_BRANCH):
    """Fetch TTL from GitHub raw and parse into an rdflib Graph."""
    raw_url = f"{GITHUB_RAW_BASE}/{branch}/{path}"
    resp = requests.get(raw_url)
    resp.raise_for_status()

    g = Graph()
    g.parse(data=resp.text, format="turtle")
    return g


def load_graph_from_upload(uploaded_file, fmt: str | None = None):
    """
    Parse an uploaded ontology file (ttl/owl/rdf/xml) into an rdflib Graph.
    If fmt is None, try to guess from the file extension.
    """
    data = uploaded_file.read()
    text = data.decode("utf-8", errors="ignore")

    name = uploaded_file.name.lower()

    if fmt is None:
        if name.endswith(".ttl"):
            fmt = "turtle"
        elif name.endswith((".owl", ".rdf", ".xml")):
            fmt = "xml"  # RDF/XML, common for OWL
        else:
            # reasonable default guess
            fmt = "turtle"

    g = Graph()
    g.parse(data=text, format=fmt)
    return g



def get_label(graph: Graph, uri):
    """Return rdfs:label or last fragment of IRI."""
    label = graph.value(uri, RDFS.label)
    if label:
        return str(label)
    # fallback: fragment after # or /
    s = str(uri)
    return s.split("#")[-1].split("/")[-1]


def get_comment(graph: Graph, uri):
    comment = graph.value(uri, RDFS.comment)
    return str(comment) if comment else ""


def extract_classes(graph: Graph):
    """Return DataFrame of classes."""
    rows = []
    # owl:Class and rdfs:Class
    for c in set(
        list(graph.subjects(RDF.type, OWL.Class))
        + list(graph.subjects(RDF.type, RDFS.Class))
    ):
        label = get_label(graph, c)
        comment = get_comment(graph, c)
        parents = [get_label(graph, p) for p in graph.objects(c, RDFS.subClassOf)]
        rows.append(
            {
                "Label": label,
                "IRI": str(c),
                "SubClassOf": ", ".join(parents),
                "Comment": comment,
            }
        )
    df = pd.DataFrame(rows).sort_values("Label")
    return df.reset_index(drop=True)


def extract_properties(graph: Graph):
    """Return DataFrames for object and datatype properties."""
    obj_rows = []
    dt_rows = []

    for p in graph.subjects(RDF.type, OWL.ObjectProperty):
        obj_rows.append(_property_row(graph, p))

    for p in graph.subjects(RDF.type, OWL.DatatypeProperty):
        dt_rows.append(_property_row(graph, p))

    df_obj = pd.DataFrame(obj_rows).sort_values("Label") if obj_rows else pd.DataFrame()
    df_dt = pd.DataFrame(dt_rows).sort_values("Label") if dt_rows else pd.DataFrame()
    return df_obj.reset_index(drop=True), df_dt.reset_index(drop=True)


def _property_row(graph: Graph, p, kind: str):
    label = get_label(graph, p)
    comment = get_comment(graph, p)
    domains = [get_label(graph, d) for d in graph.objects(p, RDFS.domain)]
    ranges = [get_label(graph, r) for r in graph.objects(p, RDFS.range)]
    return {
        "Label": label,
        "IRI": str(p),
        "Kind": kind,
        "Domain": ", ".join(domains),
        "Range": ", ".join(ranges),
        "Comment": comment,
    }


def extract_properties(graph: Graph) -> pd.DataFrame:
    """
    Return DataFrame of properties, trying to be robust to:
    - owl:ObjectProperty
    - owl:DatatypeProperty
    - owl:AnnotationProperty
    - rdf:Property
    - Untyped properties that have rdfs:domain or rdfs:range

    The DataFrame has a 'Kind' column indicating the inferred type.
    """
    props = set()

    # Explicit types
    for p in graph.subjects(RDF.type, OWL.ObjectProperty):
        props.add(p)
    for p in graph.subjects(RDF.type, OWL.DatatypeProperty):
        props.add(p)
    for p in graph.subjects(RDF.type, OWL.AnnotationProperty):
        props.add(p)
    for p in graph.subjects(RDF.type, RDF.Property):
        props.add(p)

    # Also anything with a domain or range
    for p in graph.subjects(RDFS.domain, None):
        props.add(p)
    for p in graph.subjects(RDFS.range, None):
        props.add(p)

    rows = []
    for p in props:
        types = set(graph.objects(p, RDF.type))

        if OWL.ObjectProperty in types:
            kind = "Object"
        elif OWL.DatatypeProperty in types:
            kind = "Datatype"
        elif OWL.AnnotationProperty in types:
            kind = "Annotation"
        elif RDF.Property in types:
            kind = "Generic"
        else:
            # Untyped, but used in domain/range
            kind = "Unknown"

        rows.append(_property_row(graph, p, kind=kind))

    if not rows:
        # Always return a DataFrame, never None
        return pd.DataFrame(
            columns=["Label", "IRI", "Kind", "Domain", "Range", "Comment"]
        )

    df = pd.DataFrame(rows).sort_values(["Kind", "Label"])
    return df.reset_index(drop=True)


def run_sparql(graph: Graph, query: str):
    """Run SPARQL and return a DataFrame."""
    try:
        res = graph.query(query)
    except Exception as e:
        return None, str(e)

    rows = []
    cols = res.vars
    for row in res:
        rows.append([str(row[c]) if row[c] is not None else "" for c in cols])

    df = pd.DataFrame(rows, columns=[str(c) for c in cols])
    return df, None


# -------------------------------------------------------------------
# Streamlit UI
# -------------------------------------------------------------------

def main():
    st.set_page_config(
        page_title="DFO Salmon Ontology Playground",
        layout="wide",
    )

    st.title("DFO Salmon Ontology Playground")

    st.sidebar.header("Source")

    source_mode = st.sidebar.radio(
        "Ontology source",
        ["GitHub repo", "Upload file"],
        index=0,
    )

    g = None  # will hold the rdflib.Graph

    if source_mode == "GitHub repo":
        branch = st.sidebar.text_input("Git branch", value=DEFAULT_BRANCH)

        if st.sidebar.button("Reload TTL file list (clear cache)"):
            list_ttl_files.clear()
            load_graph_from_github.clear()
            st.sidebar.success("Cache cleared – TTL file list will refresh.")

        ttl_files = list_ttl_files(branch=branch)

        if not ttl_files:
            st.error("No .ttl files found in the /ontology directory of the repo. Check branch name or repo paths.")
            st.stop()

        ttl_label_to_path = {
            f"{f['name']} ({f['path']})": f["path"] for f in ttl_files
        }

        selected_label = st.sidebar.selectbox(
            "Ontology file (from GitHub /ontology/)",
            options=list(ttl_label_to_path.keys()),
            index=0,
        )
        selected_path = ttl_label_to_path[selected_label]

        st.sidebar.write(f"**Selected file:** `{selected_path}`")

        with st.spinner(f"Loading ontology from GitHub: {selected_path}…"):
            g = load_graph_from_github(path=selected_path, branch=branch)

        st.success("Ontology loaded from GitHub.")

    else:  # Upload file
        uploaded = st.sidebar.file_uploader(
            "Upload ontology file",
            type=["ttl", "owl", "rdf", "xml"],
        )

        fmt_choice = st.sidebar.radio(
            "File format",
            ["Auto-detect", "Turtle (.ttl)", "RDF/XML (.owl/.rdf/.xml)"],
            index=0,
        )

        if fmt_choice == "Auto-detect":
            fmt = None
        elif fmt_choice == "Turtle (.ttl)":
            fmt = "turtle"
        else:
            fmt = "xml"

        if uploaded is None:
            st.warning("Upload a .ttl or .owl file to start exploring.")
            st.stop()

        with st.spinner(f"Parsing uploaded ontology: {uploaded.name}…"):
            try:
                g = load_graph_from_upload(uploaded, fmt=fmt)
            except Exception as e:
                st.error(f"Failed to parse uploaded file: {e}")
                st.stop()

        st.success(f"Ontology loaded from upload: `{uploaded.name}`")

    # from here on, the rest of your code uses `g` as before
    # After g is successfully loaded (GitHub or upload), compute classes once
    df_classes_all = extract_classes(g)

    # # Initialize a global focus class in session state (if not set yet)
    # if "focus_class_iri" not in st.session_state:
    #     if not df_classes_all.empty:
    #         st.session_state["focus_class_iri"] = df_classes_all.iloc[0]["IRI"]
    #     else:
    #         st.session_state["focus_class_iri"] = None

    # Tabs
    tab_overview, tab_classes, tab_props, tab_graph, tab_sparql = st.tabs(
    ["Overview", "Classes", "Properties", "Graph", "SPARQL"]
    )
    
    # ----------------------------------------------------------------
    # Overview
    # ----------------------------------------------------------------
    with tab_overview:
        st.subheader("Ontology overview")

        # Basic stats
        num_triples = len(g)
        num_classes = len(
            set(list(g.subjects(RDF.type, OWL.Class)) + list(g.subjects(RDF.type, RDFS.Class)))
        )
        num_obj_props = len(list(g.subjects(RDF.type, OWL.ObjectProperty)))
        num_dt_props = len(list(g.subjects(RDF.type, OWL.DatatypeProperty)))

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Triples", num_triples)
        col2.metric("Classes", num_classes)
        col3.metric("Object properties", num_obj_props)
        col4.metric("Datatype properties", num_dt_props)

        # Try to grab some ontology metadata if present
        st.markdown("### Metadata (best-effort)")

        # Heuristic: any subject typed as owl:Ontology
        ontos = list(g.subjects(RDF.type, OWL.Ontology))
        if ontos:
            onto = ontos[0]
            from rdflib.namespace import DCTERMS

            base_iri = str(onto)
            version_info = g.value(onto, OWL.versionInfo)
            version_iri = g.value(onto, OWL.versionIRI)
            title = g.value(onto, DCTERMS.title) or g.value(onto, RDFS.label)
            comment = g.value(onto, RDFS.comment)

            st.write(f"**Ontology IRI:** `{base_iri}`")
            if version_info:
                st.write(f"**Version info:** {version_info}")
            if version_iri:
                st.write(f"**Version IRI:** `{version_iri}`")
            if title:
                st.write(f"**Title:** {title}")
            if comment:
                st.write(f"**Description:** {comment}")
        else:
            st.info("No explicit `owl:Ontology` node found – showing only high-level stats.")

        st.markdown(
            """
            You can explore:
            - **Classes**: hierarchy, labels, definitions  
            - **Properties**: domains/ranges and descriptions  
            - **SPARQL**: run your own queries against the loaded ontology  
            """
        )

    # ----------------------------------------------------------------
    # Classes
    # ----------------------------------------------------------------
    with tab_classes:
        st.subheader("Classes")

        df_classes = df_classes_all

        if df_classes.empty:
            st.info("No classes found in this ontology.")
        else:
            st.markdown("Use the filter below to search by label or IRI.")

            search = st.text_input(
                "Filter by label or IRI (contains):",
                value="",
                placeholder="e.g. EscapementMethod, Stock, CU…",
            )

            if search:
                mask = (
                    df_classes["Label"].str.contains(search, case=False, na=False)
                    | df_classes["IRI"].str.contains(search, case=False, na=False)
                )
                df_filtered = df_classes[mask]
            else:
                df_filtered = df_classes

            st.caption(f"Showing {len(df_filtered)} of {len(df_classes)} classes.")

            st.dataframe(
                df_filtered,
                width="stretch",
                hide_index=True,
                height=600,
            )

    # ----------------------------------------------------------------
    # Properties
    # ----------------------------------------------------------------
    with tab_props:
        st.subheader("Properties")

        df_props = extract_properties(g)

        if df_props.empty:
            st.info(
                "No properties could be detected. "
                "This can happen if the ontology does not declare any "
                "owl:ObjectProperty / owl:DatatypeProperty / rdf:Property "
                "or domain/range axioms in this file."
            )
        else:
            kinds = sorted(df_props["Kind"].unique())
            kind_filter = st.multiselect(
                "Filter by property kind",
                options=kinds,
                default=kinds,
            )

            df_filtered = df_props[df_props["Kind"].isin(kind_filter)]

            search = st.text_input(
                "Filter properties by label or IRI (contains):",
                value="",
                key="props_search",
            )
            if search:
                mask = (
                    df_filtered["Label"].str.contains(search, case=False, na=False)
                    | df_filtered["IRI"].str.contains(search, case=False, na=False)
                )
                df_filtered = df_filtered[mask]

            st.caption(f"Showing {len(df_filtered)} of {len(df_props)} properties.")
            st.dataframe(
                df_filtered,
                width="stretch",
                hide_index=True,
                height=600,
            )

    # ----------------------------------------------------------------
    # Graph
    # ----------------------------------------------------------------
    with tab_graph:
        st.subheader("Graph views")

        df_classes = df_classes_all
        df_props = extract_properties(g)

        if df_classes.empty and df_props.empty:
            st.info("No classes or properties found to build graphs.")
        else:
            graph_mode = st.radio(
                "Graph mode",
                ["Class hierarchy", "Property-centric"],
                index=0,
                horizontal=True,
            )

            # -------------------------------
            # Mode 1: Class hierarchy
            # -------------------------------
            if graph_mode == "Class hierarchy":
                if df_classes.empty:
                    st.info("No classes found to build a class hierarchy graph.")
                else:
                    focus_options = []
                    for _, row in df_classes.iterrows():
                        label = row["Label"] or ""
                        iri = row["IRI"]
                        frag = iri.split("#")[-1].split("/")[-1]
                        display = f"{label} ({frag})" if label else iri
                        focus_options.append((display, iri))

                    focus_options_sorted = sorted(focus_options, key=lambda x: x[0])
                    display_labels = [d for d, _ in focus_options_sorted]
                    iri_lookup = {d: iri for d, iri in focus_options_sorted}

                    selected_focus_display = st.selectbox(
                        "Select focus class",
                        options=display_labels,
                        index=0,
                    )
                    focus_iri = iri_lookup[selected_focus_display]
                    focus_uri = URIRef(focus_iri)

                    max_depth = st.slider(
                        "Neighbourhood depth (how far up/down to explore)",
                        min_value=1,
                        max_value=4,
                        value=2,
                    )

                    st.write(f"**Focus IRI:** `{focus_iri}`")

                    with st.spinner("Building class hierarchy graph…"):
                        G = build_class_subclass_graph(g, focus_uri, max_depth=max_depth)

                    # Offer download of this neighbourhood as JSON
                    graph_json = json.dumps(graph_to_json_dict(G), indent=2)
                    st.download_button(
                        "Download neighbourhood as JSON",
                        data=graph_json,
                        file_name="class_neighbourhood.json",
                        mime="application/json",
                    )

                    if len(G.nodes) == 0:
                        st.info("No neighbourhood found for this class.")
                    else:
                        col_graph, col_details = st.columns([2, 1])

                        with col_graph:
                            st.markdown("#### Class hierarchy graph")
                            html = render_graph_pyvis(G, height="600px")
                            components.html(html, height=600, scrolling=True)

                            st.markdown(
                                """
                                **Legend**  
                                - 🟡 Focus class  
                                - 🔵 Ancestors  
                                - 🟢 Descendants  
                                - ⚪ Other
                                """
                            )

                        with col_details:
                            st.markdown("#### Node details")

                            node_options = []
                            for node, data in G.nodes(data=True):
                                label = data.get("label", "")
                                frag = node.split("#")[-1].split("/")[-1]
                                display = f"{label} ({frag})" if label else node
                                node_options.append((display, node))

                            node_options_sorted = sorted(node_options, key=lambda x: x[0])
                            node_display_labels = [d for d, _ in node_options_sorted]
                            node_lookup = {d: iri for d, iri in node_options_sorted}

                            default_node_index = 0
                            for i, (display, iri) in enumerate(node_options_sorted):
                                if iri == focus_iri:
                                    default_node_index = i
                                    break

                            selected_node_display = st.selectbox(
                                "Select node to inspect",
                                options=node_display_labels,
                                index=default_node_index,
                            )
                            selected_node_iri = node_lookup[selected_node_display]

                            details = describe_node(g, selected_node_iri)
                            role = G.nodes[selected_node_iri].get("role", "other")

                            st.write(f"**Label:** {details['label']}")
                            st.write(f"**IRI:** `{details['iri']}`")
                            st.write(f"**Role in graph:** `{role}`")

                            if details["comment"]:
                                st.markdown("**Comment / definition:**")
                                st.write(details["comment"])

                            if details["types"]:
                                st.markdown("**rdf:type:**")
                                for t in details["types"]:
                                    st.write(f"- `{t}`")

                            if details["parents"]:
                                st.markdown("**Parents (rdfs:subClassOf):**")
                                for p in details["parents"]:
                                    st.write(f"- {p}")

                            if details["children"]:
                                st.markdown("**Children (rdfs:subClassOf):**")
                                for c in details["children"]:
                                    st.write(f"- {c}")

                            if details["props_as_domain"]:
                                st.markdown("**Properties where this is the domain:**")
                                for p in details["props_as_domain"]:
                                    st.write(f"- {p}")

                            if details["props_as_range"]:
                                st.markdown("**Properties where this is the range:**")
                                for p in details["props_as_range"]:
                                    st.write(f"- {p}")

            # -------------------------------
            # Mode 2: Property-centric
            # -------------------------------
            else:
                if df_props.empty:
                    st.info(
                        "No properties detected to build a property-centric graph "
                        "(try another ontology or ensure properties have domain/range/type)."
                    )
                else:
                    st.markdown("Visualize a property with its domain and range classes.")

                    prop_options = []
                    for _, row in df_props.iterrows():
                        label = row["Label"] or ""
                        iri = row["IRI"]
                        frag = iri.split("#")[-1].split("/")[-1]
                        kind = row["Kind"]
                        display = f"[{kind}] {label} ({frag})" if label else f"[{kind}] {iri}"
                        prop_options.append((display, iri))

                    prop_options_sorted = sorted(prop_options, key=lambda x: x[0])
                    display_labels = [d for d, _ in prop_options_sorted]
                    iri_lookup = {d: iri for d, iri in prop_options_sorted}

                    selected_prop_display = st.selectbox(
                        "Select property",
                        options=display_labels,
                        index=0,
                    )
                    prop_iri = iri_lookup[selected_prop_display]
                    prop_uri = URIRef(prop_iri)

                    st.write(f"**Property IRI:** `{prop_iri}`")

                    with st.spinner("Building property-centric graph…"):
                        G = build_property_graph(g, prop_uri)
                    
                    graph_json = json.dumps(graph_to_json_dict(G), indent=2)
                    st.download_button(
                        "Download property graph as JSON",
                        data=graph_json,
                        file_name="property_graph.json",
                        mime="application/json",
                    )

                    if len(G.nodes) == 0:
                        st.info("No domain or range classes found for this property.")
                    else:
                        col_graph, col_details = st.columns([2, 1])

                        with col_graph:
                            st.markdown("#### Property-centric graph")
                            html = render_graph_pyvis(G, height="600px")
                            components.html(html, height=600, scrolling=True)

                            st.markdown(
                                """
                                **Legend**  
                                - 🟧 Property  
                                - 🟪 Domain class  
                                - 🟦 Range class  
                                """
                            )

                        with col_details:
                            st.markdown("#### Property details")

                            # Basic details from df_props
                            prop_row = df_props[df_props["IRI"] == prop_iri].iloc[0]

                            st.write(f"**Label:** {prop_row['Label']}")
                            st.write(f"**Kind:** {prop_row['Kind']}")
                            st.write(f"**Domain:** {prop_row['Domain']}")
                            st.write(f"**Range:** {prop_row['Range']}")

                            if prop_row["Comment"]:
                                st.markdown("**Comment / definition:**")
                                st.write(prop_row["Comment"])


    # ----------------------------------------------------------------
    # SPARQL
    # ----------------------------------------------------------------
    with tab_sparql:
        st.subheader("SPARQL playground")

        example_queries = {
            "List all classes (label + IRI)": """
                PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                PREFIX owl:  <http://www.w3.org/2002/07/owl#>

                SELECT ?class ?label
                WHERE {
                  ?class a owl:Class .
                  OPTIONAL { ?class rdfs:label ?label . }
                }
                ORDER BY ?label
            """,
            "List properties with domain & range": """
                PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                PREFIX owl:  <http://www.w3.org/2002/07/owl#>

                SELECT ?prop ?kind ?label ?domain ?range
                WHERE {
                  ?prop a ?t .
                  FILTER(?t IN (owl:ObjectProperty, owl:DatatypeProperty, rdf:Property, owl:AnnotationProperty))

                  BIND(
                    IF(?t = owl:ObjectProperty, "Object",
                      IF(?t = owl:DatatypeProperty, "Datatype",
                        IF(?t = owl:AnnotationProperty, "Annotation", "Generic")
                      )
                    ) AS ?kind
                  )

                  OPTIONAL { ?prop rdfs:label ?label . }
                  OPTIONAL { ?prop rdfs:domain ?domain . }
                  OPTIONAL { ?prop rdfs:range ?range . }
                }
                ORDER BY ?kind ?label
            """,
            "DFO: all EscapementMethod subclasses": """
                PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                PREFIX owl:  <http://www.w3.org/2002/07/owl#>
                PREFIX dfo:  <https://w3id.org/dfo/salmon#>

                SELECT ?method ?label
                WHERE {
                  ?method rdfs:subClassOf* dfo:EscapementMethod .
                  OPTIONAL { ?method rdfs:label ?label . }
                }
                ORDER BY ?label
            """,
            "DFO: MU → CU → Stock chain": """
                PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                PREFIX dfo:  <https://w3id.org/dfo/salmon#>

                SELECT ?mu ?muLabel ?cu ?cuLabel ?stock ?stockLabel
                WHERE {
                  ?mu a dfo:ManagementUnit .
                  OPTIONAL { ?mu rdfs:label ?muLabel . }

                  ?cu dfo:isMemberOfMU ?mu .
                  OPTIONAL { ?cu rdfs:label ?cuLabel . }

                  ?stock dfo:isMemberOfCU ?cu .
                  OPTIONAL { ?stock rdfs:label ?stockLabel . }
                }
                ORDER BY ?muLabel ?cuLabel ?stockLabel
            """,
        }


        selected_example = st.selectbox(
            "Example query",
            options=["(None)"] + list(example_queries.keys()),
        )

        if selected_example != "(None)":
            query_default = example_queries[selected_example]
        else:
            query_default = "SELECT * WHERE { ?s ?p ?o } LIMIT 25"

        query_text = st.text_area(
            "SPARQL query",
            value=query_default,
            height=220,
        )

        if st.button("Run query"):
            with st.spinner("Running SPARQL query…"):
                df_res, err = run_sparql(g, query_text)

            if err:
                st.error(f"SPARQL error: {err}")
            elif df_res is not None and not df_res.empty:
                st.success(f"Query returned {len(df_res)} rows.")
                st.dataframe(df_res, width='stretch')
            else:
                st.info("Query returned no results.")


if __name__ == "__main__":
    main()
