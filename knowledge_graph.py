"""
Knowledge Graph builder: text -> (subject, relation, object) triples -> graph.

Two extraction methods:
  - "spacy": classic NLP (NER + dependency parsing). Free, offline, fast; less accurate.
  - "llm":   an LLM extracts triples as JSON. More accurate on complex text; needs an API key.

Install:
    pip install spacy networkx pyvis anthropic
    python -m spacy download en_core_web_sm

Usage:
    python knowledge_graph.py                          # runs on built-in sample text with spaCy
    python knowledge_graph.py --input doc.txt --method llm --out graph.html
    (for --method llm, set ANTHROPIC_API_KEY in your environment)
"""

import argparse
import json # Đọc kết quả JSON mà LLM trả về (Block 2).
import os
import re #Regex
from collections import namedtuple

import networkx as nx # vẽ graph

# OOP , khai báo đối tượng là Triple
Triple = namedtuple("Triple", ["subject", "relation", "object"])


# --------------------------------------------------------------------------
# 1. Extraction — classic NLP (spaCy)
# --------------------------------------------------------------------------
def _clean(name):
    return re.sub(r"^(the|a|an)\s+", "", name.strip(), flags=re.I)

# tìm entity
def _span_text(token):
    """Expand a head token to its full noun phrase (prefer the named-entity span)."""
    for ent in token.doc.ents:
        if ent.start <= token.i < ent.end:
            return _clean(ent.text)
    keep = {"compound", "amod", "nummod", "poss", "flat", "nmod"} # định nghĩa đối tượng của từ
    words = [t for t in token.subtree if t.dep_ in keep or t == token]
    words = [t for t in words if t.i <= token.i]  # keep left-side modifiers only
    return _clean(" ".join(t.text for t in sorted(words, key=lambda t: t.i)))


def extract_triples_spacy(text, model="en_core_web_sm"):
    '''
    Hàm chính: spaCy phân tích ngữ pháp từng câu, tìm động từ, rồi tìm chủ ngữ (subject) gắn với động từ đó. 
    '''
    import spacy # NLP: tách câu, nhận diện tên riêng (người, công ty, địa điểm) và phân tích ngữ pháp

    nlp = spacy.load(model)
    doc = nlp(text)
    triples = []

    '''
    How Spacy works: “Elon Musk founded SpaceX in 2002.”
    "found" -> "Musk" is subject, "SpaceX" is object, "in" là giới từ
    Mục đích line 64-96: biến các câu classified vô từng tuple

    '''

    for sent in doc.sents:
        for tok in sent:
            if tok.pos_ not in ("VERB", "AUX"): # chỉ xét động từ 
                continue
            subjects = [c for c in tok.children if c.dep_ in ("nsubj", "nsubjpass")] # tìm chủ ngữ (nsubj), hoặc chủ ngũ bị động nsubjpass
            if not subjects:
                continue

            # Direct objects / attributes:  "X founded Y", "X is Y"
            objects = [c for c in tok.children if c.dep_ in ("dobj", "attr", "oprd")] # tìm object
            rel = tok.lemma_  # đưa động từ về dạng gốc 
 
            # Prepositional objects:  "X was born in Y", "X works at Y"
            # Xử lý giới từ (in, at, by, on…)
            for prep in (c for c in tok.children if c.dep_ in ("prep", "agent")):
                for pobj in (c for c in prep.children if c.dep_ == "pobj"):
                    objects.append(pobj)
                    rel_prep = f"{tok.lemma_} {prep.text}"
                    for s in subjects:
                        triples.append(Triple(_resolve(s, doc), rel_prep, _span_text(pobj)))
                        for conj in pobj.conjuncts:
                            triples.append(Triple(_resolve(s, doc), rel_prep, _span_text(conj)))
                    objects.pop()

            for s in subjects:
                for o in objects:
                    subj = _resolve(s, doc)
                    triples.append(Triple(subj, rel, _resolve(o, doc, exclude=subj)))
                    for conj in o.conjuncts:  # "X makes A and B"
                        triples.append(Triple(_resolve(s, doc), rel, _span_text(conj)))

    entity_types = {_clean(e.text): e.label_ for e in doc.ents}
    return _dedupe(triples), entity_types #bỏ duplication


# Pronouns / generic references -> which entity types they can point to
# bảng tra đại từ: coreference resolution
_COREF = {
    "he": ("PERSON",), "she": ("PERSON",), "him": ("PERSON",), "her": ("PERSON",),
    "it": ("ORG", "PRODUCT"), "they": ("ORG", "PERSON"),
    "company": ("ORG",), "the company": ("ORG",), "firm": ("ORG",),
}


# nhận vào 1 từ, nếu k phai tên thật mà chỉ là "he"/ "she" thì hướng tới tên thật mà đại từ đó đang chỉ tới.
# ví dụ: “Neil Armstrong was born in Ohio. He joined NASA.”
def _resolve(token, doc, exclude=None):
    """Map a pronoun/generic noun to the nearest preceding entity of a compatible type."""
    text = _span_text(token)
    allowed = _COREF.get(text.lower())
    if not allowed:
        return text
    for ent in reversed([e for e in doc.ents if e.end <= token.i]):
        if ent.label_ in allowed and _clean(ent.text) != exclude:
            return _clean(ent.text)
    return text


# --------------------------------------------------------------------------
# 2. Extraction — LLM
# không có API Claude nên ko cần thiết
# --------------------------------------------------------------------------
LLM_PROMPT = """Extract a knowledge graph from the text below.
Return ONLY valid JSON with this shape:
{{
  "entities": [{{"name": "...", "type": "PERSON|ORG|LOCATION|PRODUCT|CONCEPT|EVENT|DATE|OTHER"}}],
  "triples":  [{{"subject": "...", "relation": "...", "object": "..."}}]
}}
Rules:
- Use short, canonical entity names (resolve pronouns and aliases to one name).
- Relations are short lowercase verb phrases, e.g. "founded", "headquartered in", "acquired".
- Every subject/object must appear in "entities".

Text:
\"\"\"{text}\"\"\""""


def extract_triples_llm(text, model="claude-sonnet-5-5", chunk_chars=6000):
    from anthropic import Anthropic #Gọi Claude API, chỉ khi dùng method llm

    client = Anthropic()  # reads ANTHROPIC_API_KEY
    triples, entity_types = [], {}

    for chunk in _chunk_text(text, chunk_chars):
        resp = client.messages.create(
            model=model,
            max_tokens=4000,
            messages=[{"role": "user", "content": LLM_PROMPT.format(text=chunk)}],
        )
        raw = resp.content[0].text
        data = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
        for e in data.get("entities", []):
            entity_types[e["name"]] = e.get("type", "OTHER")
        for t in data.get("triples", []):
            triples.append(Triple(t["subject"], t["relation"], t["object"]))

    return _dedupe(triples), entity_types


def _chunk_text(text, size):
    """Split on paragraph boundaries so long documents fit in the context."""
    chunks, cur = [], ""
    for para in text.split("\n\n"):
        if len(cur) + len(para) > size and cur:
            chunks.append(cur)
            cur = ""
        cur += para + "\n\n"
    if cur.strip():
        chunks.append(cur)
    return chunks


def _dedupe(triples):
    seen, out = set(), []
    for t in triples:
        key = (t.subject.lower().strip(), t.relation.lower().strip(), t.object.lower().strip())
        if key not in seen and t.subject and t.object:
            seen.add(key)
            out.append(t)
    return out


# --------------------------------------------------------------------------
# 3. Build graph
# Sau khi có các tuple để tạo connection giữa entity (node) và động từ (mũi tên) và object (node)
# --------------------------------------------------------------------------
def build_graph(triples, entity_types=None):
    entity_types = entity_types or {}
    G = nx.MultiDiGraph()
    for t in triples:
        for node in (t.subject, t.object):
            if node not in G:
                G.add_node(node, type=entity_types.get(node, "OTHER"))
        G.add_edge(t.subject, t.object, relation=t.relation)
    return G


# --------------------------------------------------------------------------
# 4. Query helpers
# Tỉm kiếm mối quan hệ xung quanh các node??? 
# --------------------------------------------------------------------------
def neighbors(G, entity):
    """All facts touching an entity."""
    out = [(entity, d["relation"], v) for _, v, d in G.out_edges(entity, data=True)]
    inc = [(u, d["relation"], entity) for u, _, d in G.in_edges(entity, data=True)]
    return out + inc


def path_between(G, a, b):
    """Shortest chain of facts connecting two entities (ignoring direction)."""
    try:
        nodes = nx.shortest_path(G.to_undirected(as_view=True), a, b)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []
    facts = []
    for u, v in zip(nodes, nodes[1:]):
        if G.has_edge(u, v):
            facts.append((u, next(iter(G[u][v].values()))["relation"], v))
        else:
            facts.append((v, next(iter(G[v][u].values()))["relation"], u))
    return facts


def summary(G):
    central = sorted(nx.degree_centrality(G).items(), key=lambda x: -x[1])[:5]
    return {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "most_connected": [n for n, _ in central],
    }


# --------------------------------------------------------------------------
# 5. Export / visualize (vẽ graph)
# --------------------------------------------------------------------------
COLORS = {
    "PERSON": "#4C78A8", "ORG": "#F58518", "GPE": "#54A24B", "LOCATION": "#54A24B",
    "PRODUCT": "#B279A2", "DATE": "#9D755D", "CONCEPT": "#72B7B2", "EVENT": "#E45756",
}


def save_html(G, path="knowledge_graph.html"):
    """Interactive graph you can drag/zoom in a browser."""
    from pyvis.network import Network # Vẽ graph tương tác ra file HTML

    net = Network(height="850px", width="100%", directed=True, cdn_resources="in_line",
                  bgcolor="#ffffff", font_color="#222222")
    for node, data in G.nodes(data=True):
        net.add_node(node, label=node, title=f"{node} ({data['type']})",
                     color=COLORS.get(data["type"], "#BAB0AC"),
                     size=18 + 5 * G.degree(node))
    for u, v, data in G.edges(data=True):
        net.add_edge(u, v, label=data["relation"], title=f"{u} → {data['relation']} → {v}")

    # Always show names + relations (vis.js hides labels when zoomed out by default)
    net.set_options("""{
      "nodes": {
        "shape": "dot",
        "font": {"size": 20, "face": "arial", "strokeWidth": 3, "strokeColor": "#ffffff"},
        "scaling": {"label": {"enabled": true, "min": 16, "max": 30, "drawThreshold": 1}}
      },
      "edges": {
        "font": {"size": 15, "align": "middle", "color": "#444444",
                 "strokeWidth": 4, "strokeColor": "#ffffff"},
        "color": {"color": "#999999", "highlight": "#E45756"},
        "arrows": {"to": {"enabled": true, "scaleFactor": 0.7}},
        "smooth": {"type": "dynamic"},
        "scaling": {"label": {"drawThreshold": 1}}
      },
      "physics": {
        "barnesHut": {"gravitationalConstant": -6000, "springLength": 220, "avoidOverlap": 0.3},
        "stabilization": {"iterations": 300}
      },
      "interaction": {"hover": true, "navigationButtons": true}
    }""")
    # Write as UTF-8 ourselves (pyvis uses the OS default encoding, which breaks on Windows)
    with open(path, "w", encoding="utf-8") as f:
        f.write(net.generate_html())
    return path


def save_triples_csv(triples, path="triples.csv"):
    import csv #save_triples_csv()

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["subject", "relation", "object"])
        w.writerows(triples)
    return path


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
SAMPLE_TEXT = """Estée Lauder founded The Estée Lauder Companies in 1946.
The company is headquartered in New York City. It owns Clinique and MAC Cosmetics.
Clinique was launched in 1968. MAC Cosmetics was founded in Toronto by Frank Toskan and Frank Angelo.
The Estée Lauder Companies acquired MAC Cosmetics in 1998. Fabrizio Freda led the company as CEO."""


def main():
    p = argparse.ArgumentParser(description="Build a knowledge graph from text.")
    p.add_argument("--input", help="Path to a .txt file (default: built-in sample)")
    p.add_argument("--method", choices=["spacy", "llm"], default="spacy")
    p.add_argument("--out", default="knowledge_graph.html")
    args = p.parse_args()

    text = open(args.input, encoding="utf-8").read() if args.input else SAMPLE_TEXT

    if args.method == "llm":
        triples, types = extract_triples_llm(text)
    else:
        triples, types = extract_triples_spacy(text)

    print(f"Extracted {len(triples)} triples:")
    for t in triples:
        print(f"  ({t.subject}) -[{t.relation}]-> ({t.object})")

    G = build_graph(triples, types)
    print("\nSummary:", summary(G))

    save_triples_csv(triples, os.path.splitext(args.out)[0] + "_triples.csv")
    print("Saved:", save_html(G, args.out))


if __name__ == "__main__":
    main()
