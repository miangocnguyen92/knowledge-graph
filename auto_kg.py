"""
Auto Knowledge Graph — drop a document into a folder and its graph is drawn automatically.

Usage:
    python auto_kg.py                 # watch ./inbox, save graphs to ./graphs
    python auto_kg.py --inbox docs --outdir out --no-open

In Jupyter / other code:
    from auto_kg import draw_kg
    draw_kg("Apple was founded by Steve Jobs in Cupertino.")

Requires: knowledge_graph.py in the same folder.
    pip install spacy networkx pyvis pypdf python-docx
    python -m spacy download en_core_web_sm

Purpose: tự động hóa, chỉ cần drop file vào inbox folder là tự gọi hàm Main và tự vẽ graph
"""

import argparse
import os
import time
import webbrowser
from pathlib import Path

from knowledge_graph import (build_graph, extract_triples_spacy, save_html,
                             save_triples_csv, summary)

SUPPORTED = {".txt", ".md", ".pdf", ".docx"}


# ---------------------------------------------------------------- read files
def read_document(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="ignore")
    if ext == ".pdf":
        from pypdf import PdfReader
        return "\n\n".join(p.extract_text() or "" for p in PdfReader(path).pages)
    if ext == ".docx":
        from docx import Document
        return "\n\n".join(p.text for p in Document(path).paragraphs)
    raise ValueError(f"Unsupported file type: {ext}")


# ---------------------------------------------------------------- text -> graph
def draw_kg(text: str, out_html="knowledge_graph.html", open_browser=True):
    """One call: any text -> knowledge graph HTML file."""
    triples, types = extract_triples_spacy(text)
    if not triples:
        print("  ⚠ No relations found in this text.")
        return None
    G = build_graph(triples, types)
    save_html(G, out_html)
    save_triples_csv(triples, out_html.replace(".html", "_triples.csv"))
    print(f"  ✓ {len(triples)} relations | {summary(G)}")
    print(f"  ✓ Saved: {out_html}")
    if open_browser:
        webbrowser.open(Path(out_html).resolve().as_uri())
    return G


def process_file(path: Path, outdir: Path, open_browser: bool):
    print(f"\n📄 New file detected: {path.name}")
    try:
        text = read_document(path)
        out_html = str(outdir / f"{path.stem}_graph.html")
        draw_kg(text, out_html, open_browser)
    except Exception as e:
        print(f"  ✗ Error processing {path.name}: {e}")


# ---------------------------------------------------------------- watch folder
def watch(inbox: Path, outdir: Path, open_browser=True, interval=2.0):
    inbox.mkdir(exist_ok=True)
    outdir.mkdir(exist_ok=True)
    seen = {}  # file -> last processed modification time
    print(f"👀 Watching '{inbox}/' — drop {sorted(SUPPORTED)} files here. Press Ctrl+C to stop.")

    try:
        while True:
            for path in inbox.iterdir():
                if path.suffix.lower() not in SUPPORTED or path.name.startswith(("~", ".")):
                    continue
                mtime = path.stat().st_mtime
                if seen.get(path) == mtime:
                    continue
                time.sleep(0.5)  # wait until the file finishes copying
                if path.stat().st_mtime != mtime:
                    continue
                seen[path] = mtime
                process_file(path, outdir, open_browser)  # new or just-modified file
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Automatically draw a knowledge graph for every new document.")
    p.add_argument("--inbox", default="inbox", help="Folder to drop documents into")
    p.add_argument("--outdir", default="graphs", help="Folder to save graphs to")
    p.add_argument("--no-open", action="store_true", help="Do not open the browser automatically")
    a = p.parse_args()
    watch(Path(a.inbox), Path(a.outdir), open_browser=not a.no_open)
