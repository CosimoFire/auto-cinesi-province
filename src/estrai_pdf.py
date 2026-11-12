import sys, re, subprocess, pdfplumber
def isnum(t): return re.fullmatch(r'\d{1,3}(\.\d{3})*|\d+',t) is not None
def headers_from_text(path):
    txt=subprocess.run(['pdftotext','-layout','-l','1',path,'-'],capture_output=True,text=True,encoding='utf-8',errors='replace').stdout
    out=[]
    for line in txt.splitlines():
        if re.match(r'^\s*PROVINCIA DI\s+\d',line) or re.match(r'^\s*[A-Z\' -]+\s{2,}\d',line) and 'Totale' in "".join(out): break
        s=line.strip()
        if not s or re.search(r'MINISTERO|CENTRO ELAB|MERCATO DEL|DATI STAT|\b20\d\d\b',s): continue
        s=re.sub(r'^PROVINCIA DI\s+','',s); s=re.sub(r'^RESIDENZA\s+','',s)
        if s in('PROVINCIA DI','RESIDENZA',''): continue
        out.append(re.sub(r'\s{2,}',' ',s))
        if s.endswith('Totale') or s.endswith('TOTALE'): break
    KNOWN=['LYNK&CO','MITSUBISHI','SMART','CHRYSLER/JEEP/DODGE','CHRYSLER/JEEP/','TOTALE','ALFA ROMEO','AUDI','BMW','BYD','CHRYSLER/JEEP','DODGE','CITROEN/DS','CITROEN','CUPRA','DACIA','DR/EVO','EMC','FIAT','FORD','HONDA','HYUNDAI','JEEP','KIA','LANCIA','LAND ROVER','LEAPMOTOR','LEXUS','MASERATI','MAZDA','MERCEDES','MG','MINI','NISSAN','OMODA/JAECOO','OPEL','PEUGEOT','PORSCHE','RENAULT','SEAT','SKODA','SUBARU','SUZUKI','TESLA MOTORS','TOYOTA/LEXUS','TOYOTA','VOLKSWAGEN','VOLVO','ALTRE','Totale']
    res=[]
    for s in out:
        m=[k for k in KNOWN if s==k or s.endswith(' '+k)]
        if m: res.append(max(m,key=len))
    if 'DODGE' in res:
        res.remove('DODGE')
        for c in ('CHRYSLER/JEEP','CHRYSLER/JEEP/'):
            if c in res: res[res.index(c)]='CHRYSLER/JEEP/DODGE'
    res=['Totale' if r=='TOTALE' else r for r in res]
    return res
def words(p, xtol):
    out=[]
    for w in p.extract_words(x_tolerance=xtol):
        t=w['text']
        if re.fullmatch(r'\d[\d.]*,00', t):
            cw=(w['x1']-w['x0'])/len(t); w=dict(w); w['text']=t[:-3]; w['x1']=w['x1']-3*cw
        out.append(w)
    return out
def parse(path, xtol=3, H=None):
    H=H or headers_from_text(path); rows=[]
    with pdfplumber.open(path) as pdf:
        EDGES=None
        for p in pdf.pages:
            ws=words(p, xtol); tol=p.height*0.003
            for tw in ws:
                if tw['text'].upper().startswith('TOTALE') and tw['x0']<p.width*0.2:
                    E=sorted(w['x1'] for w in ws if abs(w['top']-tw['top'])<tol and isnum(w['text']))
                    while len(E)<len(H):
                        d=[E[i+1]-E[i] for i in range(len(E)-1)]; med=sorted(d)[len(d)//2]
                        i=max(range(len(d)),key=lambda i:d[i])
                        print("  ",path[-16:],"colonna vuota:",H[i+1],"gap x",round(d[i]/med,2),file=sys.stderr)
                        E.insert(i+1,E[i]+med)
                    EDGES=E
        for p in pdf.pages:
            ws=words(p, xtol)
            tol=p.height*0.003
            # data area: lines that contain >=3 numbers
            ws=sorted(ws,key=lambda w:w['top'])
            lines=[]
            for w in ws:
                if lines and w['top']-lines[-1][0]['top']<tol: lines[-1].append(w)
                else: lines.append([w])
            data=[L for L in lines if sum(isnum(w['text']) for w in L)>=3]
            y0=data[0][0]['top']; ylast=data[-1][0]['top']
            body=[L for L in lines if y0-tol<=L[0]['top']<=ylast+tol*8]
            numx=[]; namemax=min(w['x0'] for L in data for w in L if isnum(w['text']))
            edges=EDGES
            if False and len(H)-2<=sum(isnum(w['text']) for w in totl[0])<=len(H):
                edges=sorted(w['x1'] for w in totl[0] if isnum(w['text']))
                while len(edges)<len(H):
                    d=[edges[i+1]-edges[i] for i in range(len(edges)-1)]
                    med=sorted(d)[len(d)//2]
                    i=max(range(len(d)),key=lambda i:d[i])
                    if d[i]<1.6*med: break
                    print("  inserisco colonna vuota dopo",H[i],"gap",round(d[i]/med,2),file=sys.stderr)
                    edges.insert(i+1,edges[i]+med)
            elif EDGES and len(EDGES)==len(H):
                edges=EDGES
            else:
                xs=sorted(w['x1'] for L in data for w in L if isnum(w['text']))
                pitch=(xs[-1]-xs[0])/max(1,len(H)-1)
                cols=[[xs[0]]]
                for x in xs[1:]:
                    if x-cols[-1][-1]>pitch*0.35: cols.append([x])
                    else: cols[-1].append(x)
                edges=[max(c) for c in cols]
            if len(edges)!=len(H): print("WARN",path,"cols",len(edges),"headers",len(H),file=sys.stderr)
            pend=''
            for L in body:
                L=sorted(L,key=lambda w:w['x0'])
                name=" ".join(w['text'] for w in L if not isnum(w['text']))
                nw=[w for w in L if isnum(w['text'])]
                if not nw:
                    if name: pend=(pend+" "+name).strip()
                    continue
                name=(pend+" "+name).strip(); pend=''
                r=dict.fromkeys(H,0)
                for w in nw:
                    i=min(range(len(edges)),key=lambda j:abs(edges[j]-w['x1']))
                    r[H[i]]+=int(w['text'].replace('.',''))
                r['PROVINCIA']=name; rows.append(r)
            if pend: print("WARN trailing name",pend,path,file=sys.stderr)
    return H,rows
if __name__=='__main__':
    for f in sys.argv[1:]:
        H,rows=parse(f); t=H[-1]
        bad=[r['PROVINCIA'] for r in rows if sum(r[b] for b in H[:-1])!=r[t]]
        T=[r for r in rows if r['PROVINCIA'].upper().startswith('TOTALE')]
        print(f.split('/')[-1],len(H),"col",len(rows),"righe | mismatch",len(bad),bad[:4],"| TOTALE",T[0][t] if T else None,"somma",sum(r[t] for r in rows if r not in T))
