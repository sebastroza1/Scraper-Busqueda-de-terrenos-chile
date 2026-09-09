from landfinder.registry import load_sources

sources = load_sources()
print(f"OK registro: {len(sources)} entradas")
for p in ("P0","P1","P2","P3"):
    print(p, sum(s["priority"] == p for s in sources))
for kind in sorted({s["kind"] for s in sources}):
    print(kind, sum(s["kind"] == kind for s in sources))
