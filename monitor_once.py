"""
Ejecuta P0 + P1 una vez y guarda el resultado en SQLite.
Útil para programarlo cada hora en el Programador de tareas de Windows.
"""
from landfinder.registry import load_sources
from landfinder.runner import run_sources

sources = [s for s in load_sources() if s["priority"] in ("P0", "P1")]
results = run_sources(sources, timeout=12, persist=True)

ok = sum(r["technical_status"] == "OK" for r in results)
errors = sum(r["technical_status"] == "SOURCE_ERROR" for r in results)
print(f"Fin: {len(results)} fuentes | OK={ok} | SOURCE_ERROR={errors}")
