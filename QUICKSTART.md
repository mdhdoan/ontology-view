## 🧷 Quick Start (add this near the top of README)

You can paste this under the main intro, before “Key Features”:

````markdown
## ⚡ Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/<your-org>/<your-repo>.git
cd <your-repo>
````

(Optional) If this lives inside another repo, just `cd` into the folder that contains `app.py`.

---

### 2. Create and activate a virtual environment

```bash
python -m venv venv
source venv/bin/activate    # Linux/macOS
# venv\Scripts\activate     # Windows (PowerShell/CMD)
```

---

### 3.1 Install with requirements

```bash
pip install -r requirements.txt
```

### 3.2 Install with `requirements-pinned` version
```bash
pip install -r requirements-pinned.txt
```

### 3.3 Install dependencies

```bash
pip install --upgrade pip
pip install streamlit rdflib requests pandas networkx pyvis
```

---

### 4. Run the app

**Local machine:**

```bash
streamlit run app.py
```

**Remote server / VPN:**

```bash
streamlit run app.py --server.address 0.0.0.0 --server.port 8502
```

Then open in your browser:

```text
http://<REMOTE-IP>:8502
```

---

### 5. Load an ontology

In the left sidebar:

1. Choose **Ontology source**:

   * **GitHub repo** – load `.ttl` from `/ontology/*.ttl` in the configured repo
   * **Upload file** – upload `.ttl`, `.owl`, `.rdf`, or `.xml`
2. Once loaded, use the tabs:

   * **Overview** – basic stats
   * **Classes** – class table & search
   * **Properties** – property table & search
   * **Graph** – class hierarchy or property-centric graphs
   * **SPARQL** – run custom queries or use presets

That’s it — you’re exploring your ontology. 🎉

````

---

## 🐚 `setup.sh` script for prerequisites + venv

Here’s a simple script that:

- Checks for Python
- Creates a `venv`
- Activates it (for the current shell run)
- Installs the required Python packages

Save this as `setup.sh` in the repo root:

```bash
#!/usr/bin/env bash

# Simple setup script for the Ontology Viewer & Graph Explorer
# Usage:
#   chmod +x setup.sh
#   ./setup.sh

set -e

echo "=== Ontology Viewer & Graph Explorer – setup ==="

# 1) Check for python
if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON=python
else
    echo "ERROR: Python is not installed or not on PATH."
    echo "Please install Python 3.9+ and re-run this script."
    exit 1
fi

echo "Using Python: $PYTHON"

# 2) Create virtual environment if not exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment in ./venv ..."
    $PYTHON -m venv venv
else
    echo "Virtual environment ./venv already exists – skipping creation."
fi

# 3) Activate venv (for this shell run)
#    Note: this only affects the current shell where the script runs.
#    For future sessions, you'll still need to: source venv/bin/activate
if [ -f "venv/bin/activate" ]; then
    # Linux/macOS
    source venv/bin/activate
elif [ -f "venv/Scripts/activate" ]; then
    # Windows Git Bash (not guaranteed, but just in case)
    source venv/Scripts/activate
else
    echo "WARNING: Could not find venv activation script."
    echo "Please activate manually before running the app."
fi

# 4) Upgrade pip and install Python dependencies
echo "Upgrading pip and installing dependencies ..."
pip install --upgrade pip
pip install streamlit rdflib requests pandas networkx pyvis

echo "=== Setup complete! ==="
echo ""
echo "To run the app locally:"
echo "  source venv/bin/activate"
echo "  streamlit run app.py"
echo ""
echo "To run on a remote server (for VPN access, etc.):"
echo "  source venv/bin/activate"
echo "  streamlit run app.py --server.address 0.0.0.0 --server.port 8502"
echo ""
````

### How to use it

From the repo root (where `app.py` lives):

```bash
chmod +x setup.sh
./setup.sh
```

After the script finishes:

```bash
source venv/bin/activate
streamlit run app.py
```

On your remote machine, you can basically do:

```bash
git pull               # or copy the files up
./setup.sh
streamlit run app.py --server.address 0.0.0.0 --server.port 8502
```
