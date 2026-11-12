import sys, glob, re, csv, os
sys.path.insert(0, os.path.dirname(__file__)); import estrai_pdf as parse2
src, outdir = sys.argv[1], sys.argv[2]
MESI=['gennaio','febbraio','marzo','aprile','maggio','giugno','luglio','agosto','settembre','ottobre']
def key(n):
    k=re.sub(r'[^A-Z]','',n.upper())
    return 'MONZAEDELLABRIANZA' if k=='BRIANZA' else k
long=[]; canon={}
for i,f in enumerate(sorted(glob.glob(src+'/*.pdf'))):
    H,rows=parse2.parse(f); m=MESI[i]
    for r in rows:
        k=key(r['PROVINCIA'])
        if i==9 or k not in canon: canon.setdefault(k, r['PROVINCIA'] if not k.startswith('TOTALE') else 'TOTALE')
        for b in H[:-1]: long.append([i+1,m,k,b,r[b]])
        long.append([i+1,m,k,'TOTALE MESE',r[H[-1]]])
# prefer October spellings
H10,rows10=parse2.parse(sorted(glob.glob(src+'/*.pdf'))[-1])
for r in rows10: canon[key(r['PROVINCIA'])]=r['PROVINCIA'] if not r['PROVINCIA'].startswith('TOTALE') else 'TOTALE'
provs=sorted({l[2] for l in long})
print("province distinte:",len(provs), [canon[p] for p in provs if p not in {key(r['PROVINCIA']) for r in rows10}])
# Feb fix: PDF TOTALE row is missing Leapmotor -> recompute TOTALE rows as sum of provinces
for l in long:
    if l[2]=='TOTALE':
        l[4]=sum(x[4] for x in long if x[0]==l[0] and x[3]==l[3] and x[2]!='TOTALE')
# harmonised brand for wide table
HARM={'CHRYSLER/JEEP/DODGE':'JEEP','CITROEN/DS':'CITROEN','TOYOTA/LEXUS':'TOYOTA+LEXUS','TOYOTA':'TOYOTA+LEXUS','LEXUS':'TOYOTA+LEXUS'}
with open(outdir+'/immatricolazioni_provincia_marca_gen-ott2026_long.csv','w',newline='',encoding='utf-8-sig') as fh:
    w=csv.writer(fh,delimiter=';'); w.writerow(['n_mese','mese','provincia','marca_originale','marca_armonizzata','immatricolazioni'])
    for l in long: w.writerow([l[0],l[1],canon[l[2]],l[3],HARM.get(l[3],l[3]),l[4]])
brands=[]; 
for l in long:
    b=HARM.get(l[3],l[3])
    if b!='TOTALE MESE' and b not in brands: brands.append(b)
brands=sorted(brands,key=lambda b:(b=='ALTRE',b))
cum={}
for l in long: 
    b=HARM.get(l[3],l[3]); cum[(l[2],b)]=cum.get((l[2],b),0)+l[4]
with open(outdir+'/immatricolazioni_provincia_marca_gen-ott2026_cumulato.csv','w',newline='',encoding='utf-8-sig') as fh:
    w=csv.writer(fh,delimiter=';'); w.writerow(['provincia']+brands+['TOTALE'])
    for p in sorted(provs,key=lambda p:(p=='TOTALE',canon[p])):
        w.writerow([canon[p]]+[cum.get((p,b),0) for b in brands]+[cum[(p,'TOTALE MESE')]])
        if p!='TOTALE': assert sum(cum.get((p,b),0) for b in brands)==cum[(p,'TOTALE MESE')], p
# national Chinese share
CN=['BYD','MG','OMODA/JAECOO','LEAPMOTOR']; CNX=['DR/EVO','EMC']
nat={}
for l in long:
    if l[2]=='TOTALE': nat.setdefault(l[0],{})[l[3]]=l[4]
print("\nmese;totale;"+";".join(CN+CNX)+";cinesi_stretti;%;con_DR_EMC;%")
T=dict.fromkeys(['tot']+CN+CNX,0)
for n in sorted(nat):
    d=nat[n]; tot=d['TOTALE MESE']; a=sum(d.get(b,0) for b in CN); c=a+sum(d.get(b,0) for b in CNX)
    T['tot']+=tot
    for b in CN+CNX: T[b]+=d.get(b,0)
    print(f"{MESI[n-1]};{tot};"+";".join(str(d.get(b,0)) for b in CN+CNX)+f";{a};{100*a/tot:.2f};{c};{100*c/tot:.2f}")
a=sum(T[b] for b in CN); c=a+sum(T[b] for b in CNX)
print(f"GEN-OTT;{T['tot']};"+";".join(str(T[b]) for b in CN+CNX)+f";{a};{100*a/T['tot']:.2f};{c};{100*c/T['tot']:.2f}")
for b in CN+CNX: print(b, T[b], f"{100*T[b]/T['tot']:.2f}%")

