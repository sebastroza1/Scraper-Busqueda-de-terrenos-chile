from .probes import probe_source
from .storage import save_result

def run_sources(sources, timeout=12, persist=True, callback=None):
    results = []
    total = len(sources)
    for i, source in enumerate(sources, 1):
        result = probe_source(source, timeout).to_dict()
        results.append(result)
        if persist:
            save_result(result)
        if callback:
            callback(i, total, source, result)
    return results
