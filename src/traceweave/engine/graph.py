"""Small deterministic graph and explicit entity links."""
from dataclasses import dataclass
@dataclass(frozen=True)
class EntityLink:
    source: str; target: str; relation: str; evidence_id: str
class EvidenceGraph:
    def __init__(self): self.nodes=set(); self.links=[]
    def add_record(self,record):
        self.nodes.add(record.id)
        for c in record.claims:
            self.nodes.add(str(c.object)); self.links.append(EntityLink(record.id,str(c.object),c.predicate,record.id))
    def as_dict(self): return {"nodes":sorted(self.nodes),"links":[{**l.__dict__, "provenance":[l.evidence_id]} for l in sorted(self.links,key=lambda x:(x.source,x.target,x.relation,x.evidence_id))]}
