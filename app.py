import requests
import streamlit as st
import pandas as pd
from rdflib import Graph, RDF, RDFS, OWL, Namespace

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


def _property_row(graph: Graph, p):
    label = get_label(graph, p)
    comment = get_comment(graph, p)
    domains = [get_label(graph, d) for d in graph.objects(p, RDFS.domain)]
    ranges = [get_label(graph, r) for r in graph.objects(p, RDFS.range)]
    return {
        "Label": label,
        "IRI": str(p),
        "Domain": ", ".join(domains),
        "Range": ", ".join(ranges),
        "Comment": comment,
    }


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

    # Sidebar: repo/branch/file
    st.sidebar.header("Source")

    branch = st.sidebar.text_input("Git branch", value=DEFAULT_BRANCH)

    if st.sidebar.button("Reload TTL file list (clear cache)"):
        list_ttl_files.clear()
        load_graph_from_github.clear()
        st.sidebar.success("Cache cleared – TTL file list will refresh.")

    ttl_files = list_ttl_files(branch=branch)

    if not ttl_files:
        st.error("No .ttl files found in the repo. Check branch name or repo paths.")
        st.stop()

    ttl_label_to_path = {f"{f['name']} ({f['path']})": f["path"] for f in ttl_files}

    selected_label = st.sidebar.selectbox(
        "Ontology file",
        options=list(ttl_label_to_path.keys()),
        index=0,
    )
    selected_path = ttl_label_to_path[selected_label]

    st.sidebar.write(f"**Selected file:** `{selected_path}`")

    with st.spinner(f"Loading ontology from {selected_path}…"):
        g = load_graph_from_github(path=selected_path, branch=branch)

    st.success("Ontology loaded from GitHub")

    # Tabs
    tab_overview, tab_classes, tab_props, tab_sparql = st.tabs(
        ["Overview", "Classes", "Properties", "SPARQL"]
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

        df_classes = extract_classes(g)

        search = st.text_input("Filter by label or IRI (contains):", value="")
        if search:
            mask = df_classes["Label"].str.contains(search, case=False, na=False) | df_classes[
                "IRI"
            ].str.contains(search, case=False, na=False)
            df_filtered = df_classes[mask]
        else:
            df_filtered = df_classes

        st.dataframe(df_filtered, use_container_width=True, hide_index=True)

    # ----------------------------------------------------------------
    # Properties
    # ----------------------------------------------------------------
    with tab_props:
        st.subheader("Properties")

        df_obj, df_dt = extract_properties(g)

        st.markdown("### Object properties")
        if df_obj.empty:
            st.info("No owl:ObjectProperty definitions found.")
        else:
            search_obj = st.text_input(
                "Filter object properties (label or IRI):", key="search_obj"
            )
            df_o = df_obj
            if search_obj:
                mask = df_o["Label"].str.contains(search_obj, case=False, na=False) | df_o[
                    "IRI"
                ].str.contains(search_obj, case=False, na=False)
                df_o = df_o[mask]
            st.dataframe(df_o, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("### Datatype properties")
        if df_dt.empty:
            st.info("No owl:DatatypeProperty definitions found.")
        else:
            search_dt = st.text_input(
                "Filter datatype properties (label or IRI):", key="search_dt"
            )
            df_d = df_dt
            if search_dt:
                mask = df_d["Label"].str.contains(search_dt, case=False, na=False) | df_d[
                    "IRI"
                ].str.contains(search_dt, case=False, na=False)
                df_d = df_d[mask]
            st.dataframe(df_d, use_container_width=True, hide_index=True)

    # ----------------------------------------------------------------
    # SPARQL
    # ----------------------------------------------------------------
    with tab_sparql:
        st.subheader("SPARQL playground")

        example_queries = {
            "List all classes (label + IRI)": """
                SELECT ?class ?label
                WHERE {
                  ?class a owl:Class .
                  OPTIONAL { ?class rdfs:label ?label . }
                }
                ORDER BY ?label
            """,
            "List object properties with domain & range": """
                SELECT ?prop ?label ?domain ?range
                WHERE {
                  ?prop a owl:ObjectProperty .
                  OPTIONAL { ?prop rdfs:label ?label . }
                  OPTIONAL { ?prop rdfs:domain ?domain . }
                  OPTIONAL { ?prop rdfs:range ?range . }
                }
                ORDER BY ?label
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
                st.dataframe(df_res, use_container_width=True)
            else:
                st.info("Query returned no results.")


if __name__ == "__main__":
    main()
