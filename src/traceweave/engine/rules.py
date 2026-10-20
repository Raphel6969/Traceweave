"""YAML/JSON correlation rule loading without imposing a runtime CLI."""
import json
def load_rules(text):
    try:
        import yaml
        value=yaml.safe_load(text)
        return value if isinstance(value,list) else value.get("rules",[])
    except ImportError:
        # Minimal YAML subset: a list of flat key/value mappings.
        out=[]; current=None
        for line in text.splitlines():
            line=line.strip()
            if line.startswith("- "):
                if current: out.append(current)
                current={}; line=line[2:]
            if ":" in line:
                k,v=line.split(":",1); current=current or {}; current[k.strip()]=v.strip().strip("\"'")
        if current: out.append(current)
        return out
