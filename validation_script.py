import json
import random
import os

def export_test_config(num_vars, num_clauses, seed=42):
    """Exports the symbolic field parameters so Rust can use the EXACT same 'site conditions'."""
    random.seed(seed)
    symbolic_field = [random.gauss(0, 1) for _ in range(num_vars)]
    # We'll save this so Claude's Rust code can read it for a bit-for-bit match
    config = {
        "num_vars": num_vars,
        "num_clauses": num_clauses,
        "symbolic_field": symbolic_field,
        "seed": seed
    }
    
    os.makedirs("Heuristics", exist_ok=True)
    with open("Heuristics/site_config.json", "w") as f:
        json.dump(config, f)
    print("Site configuration exported for Rust synchronization.")

export_test_config(100, 400)
