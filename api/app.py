"""TraceWeave local API. SQLite is the sole persistence layer."""
from __future__ import annotations
import hashlib, json, os, re, sqlite3
from pathlib import Path
from typing import Any
from fastapi import FastAPI, File, HTTPException, UploadFile, Header, Form, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from traceweave.engine import canonical_json, html_report, parse_auth_jsonl, parse_application_audit, parse_network_csv, analyze

_SAFE=re.compile(r"[^A-Za-z0-9_.-]+")
def _safe_name(n): return (_SAFE.sub("_",Path(n or "upload").name).strip("._") or "upload")[:120]
def _auth(x_api_key: str|None = Header(default=None), api_key: str|None = Query(default=None)):
    expected=os.environ.get("TRACEWEAVE_API_KEY")
    supplied = x_api_key or api_key
    if expected and supplied != expected: raise HTTPException(401,"invalid API key")
def _detect(name,text):
    low=name.lower()
    if low.endswith(('.audit','.audit.log','.app.log')): return 'application_audit'
    if low.endswith(('.csv','.conn','.conn.log','.network')) or (text.lstrip() and ',' in text.splitlines()[0] and not text.lstrip().startswith('{')): return 'network'
    if low.endswith(('.jsonl','.auth','.auth.json')): return 'auth'
    try:
        first=next(x for x in text.splitlines() if x.strip() and not x.lstrip().startswith('#')); json.loads(first); return 'auth' if any(k in first for k in ('login','auth','user')) else 'application_audit'
    except Exception: return 'application_audit'
def _parse(name,data,config):
    text=data.decode('utf-8',errors='replace'); kind=_detect(name,text); diagnostics=[]
    fn={'auth':parse_auth_jsonl,'network':parse_network_csv,'application_audit':parse_application_audit}[kind]
    if kind in {'auth','application_audit'}:
        good=[]
        for line_no,line in enumerate(text.splitlines(),1):
            if not line.strip() or line.lstrip().startswith('#'): continue
            try:
                parsed=fn(line+'\n',name,config)
                for record in parsed:
                    record.line=line_no; record.raw_line=line; record.verbatim=line
                good.extend(parsed)
            except Exception as exc: diagnostics.append({'file':name,'line':line_no,'error':str(exc)})
        return good,kind,diagnostics
    try: return fn(text,name,config),kind,diagnostics
    except Exception as exc: return [],kind,[{'file':name,'line':None,'error':str(exc)}]

def create_app(data_dir=None):
    root=Path(data_dir or os.environ.get('TRACEWEAVE_DATA_DIR','.traceweave-data')).expanduser(); root.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(root/'traceweave.sqlite3',check_same_thread=False); db.row_factory=sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript('''CREATE TABLE IF NOT EXISTS cases(id TEXT PRIMARY KEY,title TEXT,description TEXT,status TEXT,progress TEXT,analysis TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS files(case_id TEXT,name TEXT,sha256 TEXT,config TEXT,kind TEXT,PRIMARY KEY(case_id,name),FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS records(case_id TEXT,record_id TEXT,source_id TEXT,file TEXT,line INTEGER,raw_sha256 TEXT,chain_hash TEXT,previous_hash TEXT,raw_line TEXT,raw_json TEXT,event_json TEXT,provenance_json TEXT,claims_json TEXT,PRIMARY KEY(case_id,record_id),FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE);
    CREATE TABLE IF NOT EXISTS claims(case_id TEXT,claim_id TEXT,json TEXT,PRIMARY KEY(case_id,claim_id),FOREIGN KEY(case_id) REFERENCES cases(id) ON DELETE CASCADE);''')
    try: db.execute('ALTER TABLE cases ADD COLUMN analysis TEXT')
    except sqlite3.OperationalError: pass
    db.commit()
    app=FastAPI(title='TraceWeave API',version='0.3.0'); app.state.data_dir=root; app.state.db=db
    app.add_middleware(CORSMiddleware,allow_origins=[x.strip() for x in os.environ.get('TRACEWEAVE_CORS_ORIGINS','http://localhost:3000,http://127.0.0.1:3000').split(',') if x.strip()],allow_credentials=False,allow_methods=['*'],allow_headers=['*'])
    def load(cid):
        if not re.fullmatch(r'[0-9a-f]{64}',cid): raise HTTPException(404,'case not found')
        row=db.execute('SELECT * FROM cases WHERE id=?',(cid,)).fetchone()
        if not row: raise HTTPException(404,'case not found')
        records=[{'event':json.loads(r['event_json']),'id':r['record_id'],'source_id':r['source_id'],'file':r['file'],'line':r['line'],'raw_sha256':r['raw_sha256'],'chain_hash':r['chain_hash'],'raw_line':r['raw_line'],'raw_record':json.loads(r['raw_json']),'provenance':json.loads(r['provenance_json']),'claims':json.loads(r['claims_json'])} for r in db.execute('SELECT * FROM records WHERE case_id=? ORDER BY rowid',(cid,))]
        claims=[json.loads(r['json']) for r in db.execute('SELECT json FROM claims WHERE case_id=? ORDER BY claim_id',(cid,))]
        files=[]
        for r in db.execute('SELECT name,sha256,config,kind FROM files WHERE case_id=? ORDER BY name',(cid,)):
            item=dict(r); item['config']=json.loads(item['config'] or '{}'); meta=item['config'].pop('_metadata',{})
            item.update(meta); files.append(item)
        analysis=json.loads(row['analysis']) if row['analysis'] else {}
        payload={'id':cid,'title':row['title'],'description':row['description'],'status':row['status'],'progress':json.loads(row['progress']),'files':files,'records':records,'claims':claims,'chain_head':records[-1]['chain_hash'] if records else '0'*64}
        payload['timeline']=[dict(r['event'],event_id=r['id'],record_id=r['id'],state='Observed',provenance=[r['id']]) for r in records]
        payload['graph']={'nodes':sorted({r['id'] for r in records}|{str(c['object']) for c in claims}),'links':[{'source':r['id'],'target':str(c['object']),'relation':c['predicate'],'evidence_id':r['id'],'provenance':[r['id']]} for r in records for c in r.get('claims',[])]}
        payload['gaps']=analysis.get('gaps',[]); payload['contradictions']=analysis.get('contradictions',[]); payload['limitations']=analysis.get('limitations',[]); payload['confidence_breakdown']=analysis.get('confidence_breakdown',{}); payload['chain_valid']=_verify(cid)
        return payload
    def _verify(cid):
        prev='0'*64
        for r in db.execute('SELECT * FROM records WHERE case_id=? ORDER BY rowid',(cid,)):
            raw=json.loads(r['raw_json']); expected=hashlib.sha256(f'{prev}:{canonical_json(raw)}'.encode()).hexdigest()
            if r['previous_hash']!=prev or r['chain_hash']!=expected: return False
            prev=r['chain_hash']
        return True
    @app.get('/health')
    def health(): return {'status':'ok'}
    @app.post('/simulator/files')
    def simulator_files(_:None=Depends(_auth)):
        from datasets.generator import generate
        import tempfile
        with tempfile.TemporaryDirectory(prefix='traceweave-simulator-') as tmp:
            path=generate(tmp)
            return {'files':[{'name':p.name,'content':p.read_text(encoding='utf-8')} for p in sorted(path.iterdir()) if p.name != 'ground_truth.json']}

    @app.post('/cases',status_code=201)
    async def create_case(files:list[UploadFile]=File(...),config:str|None=Form(default=None),_:None=Depends(_auth)):
        if not files: raise HTTPException(400,'at least one evidence file is required')
        try: configs=json.loads(config) if config else {}
        except Exception as e: raise HTTPException(400,f'invalid config JSON: {e}')
        entries=[]; diagnostics=[]
        for f in files:
            data=await f.read(); name=_safe_name(f.filename or 'upload'); cfg=configs.get(name,configs.get(f.filename or '',configs.get('default',{})))
            try: parsed,kind,file_diagnostics=_parse(name,data,cfg); diagnostics.extend(file_diagnostics); entries.append((name,data,cfg,parsed,kind))
            except Exception as e: diagnostics.append({'file':name,'line':None,'error':str(e)}); entries.append((name,data,cfg,[],_detect(name,data.decode('utf-8','replace'))))
        manifest=[{'name':n,'sha256':hashlib.sha256(d).hexdigest()} for n,d,_,_,_ in sorted(entries)]
        cid=hashlib.sha256(canonical_json(manifest).encode()).hexdigest()
        all_records=[r for _,_,_,rs,_ in sorted(entries) for r in rs]; result=analyze(all_records,expected_sources={n for n,_,_,_,_ in entries})
        analysis={'gaps':result.gaps,'contradictions':result.contradictions,'limitations':[],'confidence_breakdown':result.confidence_breakdown}
        db.execute('INSERT OR REPLACE INTO cases(id,title,description,status,progress,analysis) VALUES(?,?,?,?,?,?)',(cid,f'TraceWeave case {cid[:12]}','Deterministic evidence reconstruction with explicit provenance.','complete',json.dumps({'status':'complete','processed':len(all_records),'total':len(all_records),'diagnostics':len(diagnostics)},sort_keys=True),json.dumps(analysis,sort_keys=True,default=str)))
        for n,d,cfg,parsed,kind in entries:
            file_errors=[item for item in diagnostics if item.get('file')==n]
            timestamps=sorted(record.event.occurred_at.isoformat() for record in parsed)
            stored_cfg=dict(cfg or {}); stored_cfg['_metadata']={'detected_format':kind,'record_count':len(parsed),'parse_errors':file_errors,'time_range':{'start':timestamps[0] if timestamps else None,'end':timestamps[-1] if timestamps else None}}
            db.execute('INSERT OR REPLACE INTO files VALUES(?,?,?,?,?)',(cid,n,hashlib.sha256(d).hexdigest(),json.dumps(stored_cfg,sort_keys=True),kind))
        prev='0'*64
        for r in result.records:
            ch=hashlib.sha256(f'{prev}:{canonical_json(r.raw_record)}'.encode()).hexdigest(); r.chain_hash=ch
            rd=r.model_dump(mode='json'); rd['id']=r.id; claim_json=[c.model_dump(mode='json') for c in r.claims]
            db.execute('INSERT OR REPLACE INTO records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(cid,r.id,r.source_id,r.file,r.line,r.raw_hash,ch,prev,r.raw_line,json.dumps(r.raw_record,sort_keys=True,ensure_ascii=False),json.dumps(rd.get('event',{}),sort_keys=True),json.dumps(rd.get('provenance',{}),sort_keys=True),json.dumps(claim_json,sort_keys=True)))
            prev=ch
        for c in result.claims:
            item=c.model_dump(mode='json'); item['claim_id']=c.stable_id; item['provenance']=sorted({r.id for r in result.records if c in r.claims or c.subject==r.id}); db.execute('INSERT OR REPLACE INTO claims VALUES(?,?,?)',(cid,item['claim_id'],json.dumps(item,sort_keys=True)))
        db.commit(); return {'id':cid,'status':'complete','file_count':len(entries),'record_count':len(all_records),'diagnostics':diagnostics,'files':load(cid)['files']}
    @app.get('/cases')
    def list_cases(_:None=Depends(_auth)): return [dict(r) for r in db.execute('SELECT id,title,description,status,progress FROM cases ORDER BY id')]
    @app.get('/cases/{cid}')
    def get_case(cid,_:None=Depends(_auth)): return {k:v for k,v in load(cid).items() if k not in ('records',)}
    for suffix,key in [('timeline','timeline'),('graph','graph'),('claims','claims'),('gaps','gaps'),('contradictions','contradictions')]:
        async def endpoint(cid,_=Depends(_auth),_key=key): return load(cid)[_key]
        app.add_api_route(f'/cases/{{cid}}/{suffix}',endpoint,methods=['GET'])
    @app.get('/cases/{cid}/claims/{claim_id}/provenance')
    def case_provenance(cid,claim_id,_:None=Depends(_auth)):
        load(cid)
        row=db.execute('SELECT json FROM claims WHERE case_id=? AND claim_id=?',(cid,claim_id)).fetchone()
        if not row: raise HTTPException(404,'claim not found')
        c=json.loads(row['json']); ids=set(c.get('provenance',[])); out=[]
        for r in db.execute('SELECT * FROM records WHERE case_id=? ORDER BY rowid',(cid,)):
            if r['record_id'] in ids: out.append({'id':r['record_id'],'source_id':r['source_id'],'file':r['file'],'line':r['line'],'raw_sha256':r['raw_sha256'],'chain_hash':r['chain_hash'],'raw_line':r['raw_line'],'raw_record':json.loads(r['raw_json']),'event':json.loads(r['event_json']),'provenance':json.loads(r['provenance_json'])})
        return {'claim_id':claim_id,'provenance':out}

    @app.get('/claims/{claim_id}/provenance')
    def provenance(claim_id,_:None=Depends(_auth)):
        row=db.execute('SELECT case_id,json FROM claims WHERE claim_id=?',(claim_id,)).fetchone()
        if not row: raise HTTPException(404,'claim not found')
        c=json.loads(row['json']); ids=set(c.get('provenance',[])); out=[]
        for r in db.execute('SELECT * FROM records WHERE case_id=? ORDER BY rowid',(row['case_id'],)):
            if r['record_id'] in ids: out.append({'id':r['record_id'],'source_id':r['source_id'],'file':r['file'],'line':r['line'],'raw_sha256':r['raw_sha256'],'chain_hash':r['chain_hash'],'raw_line':r['raw_line'],'raw_record':json.loads(r['raw_json']),'event':json.loads(r['event_json']),'provenance':json.loads(r['provenance_json'])})
        return {'claim_id':claim_id,'provenance':out}
    @app.get('/cases/{cid}/integrity')
    def integrity(cid,_=Depends(_auth)):
        load(cid); previous='0'*64; broken_index=None
        for index,r in enumerate(db.execute('SELECT * FROM records WHERE case_id=? ORDER BY rowid',(cid,))):
            raw=json.loads(r['raw_json']); expected=hashlib.sha256(f'{previous}:{canonical_json(raw)}'.encode()).hexdigest()
            if r['previous_hash']!=previous or r['chain_hash']!=expected:
                broken_index=index; break
            previous=r['chain_hash']
        return {'case_id':cid,'verified':broken_index is None,'valid':broken_index is None,'first_broken_index':broken_index,'recomputed':True}
    @app.get('/cases/{cid}/progress')
    def progress(cid,_=Depends(_auth)):
        value=load(cid)['progress']
        return StreamingResponse((f'data: {json.dumps(value,sort_keys=True)}\n\n' for _ in [0]),media_type='text/event-stream')
    @app.get('/cases/{cid}/progress/status')
    def progress_status(cid,_=Depends(_auth)): return load(cid)['progress']
    @app.get('/cases/{cid}/progress/stream')
    def progress_stream(cid,_=Depends(_auth)):
        value=load(cid)['progress']; return StreamingResponse((f'data: {json.dumps(value,sort_keys=True)}\n\n' for _ in [0]),media_type='text/event-stream')
    @app.get('/cases/{cid}/report')
    def report(cid,format='json',_=Depends(_auth)):
        c=load(cid)
        if format=='html': return HTMLResponse(html_report(c))
        if format!='json': raise HTTPException(400,'format must be json or html')
        return c
    @app.delete('/cases/{cid}',status_code=204)
    def delete(cid,_=Depends(_auth)): load(cid); db.execute('DELETE FROM cases WHERE id=?',(cid,)); db.commit()
    return app
app=create_app()
