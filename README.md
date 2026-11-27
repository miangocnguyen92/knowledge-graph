# Knowledge Graph Generator

Turn any text into an **interactive knowledge graph**, automatically.

The tool reads a document, extracts facts as **(subject → relation → object)** triples using NLP, and draws them as a graph you can drag, zoom, and explore in your browser. Drop a file into a folder and its graph appears.

**Example:** "Steve Jobs founded Apple in 1976. Apple is headquartered in Cupertino. Apple released the iPhone in 2007. Tim Cook succeeded Steve Jobs in 2011. Apple acquired Beats in 2014. Jimmy Iovine founded Beats."
<img width="1165" height="853" alt="screenshot" src="https://github.com/user-attachments/assets/bb757d92-b14d-468e-a196-8f20be7ca7db" />

---

## Features

- **Two extraction methods**
  - `spacy`: classic NLP (named-entity recognition + dependency parsing). Free, offline, fast.
  - `llm`: uses the Claude API to extract triples as JSON. More accurate on complex text.
- **Pronoun resolution**: maps *he / she / it / the company* to the most recent matching entity.
- **Auto mode**: watches an `inbox/` folder and builds a graph for every new `.txt`, `.md`, `.pdf`, or `.docx` file.
- **Interactive HTML output** (PyVis): nodes are colored by entity type and sized by number of connections.
- **CSV export** of all extracted triples for further analysis.
- **Graph queries**: neighbors of an entity, shortest path between two entities, most-connected nodes.

---

## How It Works

```
Text  ──►  Extract triples  ──►  Build graph (NetworkX)  ──►  Interactive HTML + CSV
           (spaCy or LLM)
```

**Example:** *"Estée Lauder founded The Estée Lauder Companies in 1946."*

| Subject | Relation | Object |
|---|---|---|
| Estée Lauder | found | Estée Lauder Companies |
| Estée Lauder | found in | 1946 |

1. **Extraction**: For each verb, spaCy finds its subject (`nsubj`), its objects (`dobj`, `attr`), and prepositional objects (*born **in** Ohio*). Noun phrases are expanded to full entity names.
2. **Coreference**: Pronouns are linked back to the nearest compatible entity (e.g. *He* → `PERSON`).
3. **Graph building**: Entities become nodes and relations become directed, labeled edges.
4. **Visualization**: The graph is exported to a self-contained HTML file.

---

## Project Structure

```
KnowledgeGraph/
├── knowledge_graph.py   # Core: extraction, graph building, queries, export
├── auto_kg.py           # Folder watcher: drop a file → graph is drawn automatically
├── inbox/               # Drop documents here
├── graphs/              # Generated graphs (.html) and triples (.csv)
└── requirements.txt
```

---

## Installation

```bash
git clone https://github.com/<your-username>/knowledge-graph.git
cd knowledge-graph

python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS / Linux

pip install spacy networkx pyvis pypdf python-docx anthropic
python -m spacy download en_core_web_sm
```

---

## Usage

### 1. Run on the built-in sample text
```bash
python knowledge_graph.py
```
Outputs `knowledge_graph.html` and `knowledge_graph_triples.csv`.

### 2. Run on your own file
```bash
python knowledge_graph.py --input mydoc.txt --out mygraph.html
```

### 3. Auto mode: drop files into a folder
```bash
python auto_kg.py
```
Then drop any `.txt`, `.md`, `.pdf`, or `.docx` file into `inbox/`. The graph is saved to `graphs/` and opens in your browser. Press `Ctrl+C` to stop.

| Option | Default | Description |
|---|---|---|
| `--inbox` | `inbox` | Folder to watch |
| `--outdir` | `graphs` | Folder to save graphs |
| `--no-open` | off | Don't open the browser automatically |

### 4. Use it in Python / Jupyter
```python
from auto_kg import draw_kg
draw_kg("Apple was founded by Steve Jobs in Cupertino.")
```

---

## Node Colors

| Entity type | Color |
|---|---|
| Person | 🔵 Blue |
| Organization | 🟠 Orange |
| Location | 🟢 Green |
| Product | 🟣 Purple |
| Date | 🟤 Brown |
| Event | 🔴 Red |

---

## Limitations

- The spaCy method is rule-based, so it works best on short, factual sentences and can miss relations in complex or passive phrasing.
- Coreference resolution is a simple heuristic (nearest matching entity), not a full model.
- Entities with different spellings (e.g. *MAC* vs *MAC Cosmetics*) are not merged.

## Future Improvements

- Entity merging / alias resolution
- Support for more languages (e.g. Vietnamese, Chinese, etc.)
- A simple web UI for pasting text directly

---

## 🛠️ Tech Stack

Python · spaCy · NetworkX · PyVis · pypdf · python-docx

## Author

**Mia Nguyen**: [GitHub](https://github.com/miangocnguyen92) · [LinkedIn](https://www.linkedin.com/in/mianguyen92/) · [Portfolio](https://mia-nguyen-portfolio.lovable.app/)
