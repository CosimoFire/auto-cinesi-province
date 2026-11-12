import csv,sys
rows=list(csv.DictReader(open(sys.argv[1],encoding='utf-8-sig'),delimiter=';'))
CN=['BYD','MG','OMODA/JAECOO','LEAPMOTOR']; IT=['DR/EVO','EMC']
out=[]
for r in rows:
    t=int(r['TOTALE']); cn=sum(int(r[b]) for b in CN); it=sum(int(r[b]) for b in IT); a=int(r['ALTRE'])
    out.append(dict(p=r['provincia'],tot=t,cn=cn,it=it,altre=a,
        q=100*cn/t,q2=100*(cn+it)/t,qa=100*a/t,max=100*(cn+it+a)/t, **{b:int(r[b]) for b in CN+IT}))
nat=[o for o in out if o['p']=='TOTALE'][0]; out=[o for o in out if o['p']!='TOTALE']
print("ITALIA tot",nat['tot'],"cn",nat['cn'],f"{nat['q']:.2f}","+DR/EMC",f"{nat['q2']:.2f}","ALTRE",nat['altre'],f"{nat['qa']:.2f}%")
qa=sorted(o['qa'] for o in out); print("ALTRE % per provincia: min",round(qa[0],2),"mediana",round(qa[53],2),"max",round(qa[-1],2))
print("province con ALTRE >2%:",[(o['p'],round(o['qa'],1),o['altre']) for o in sorted(out,key=lambda o:-o['qa']) if o['qa']>2])
r1=sorted(out,key=lambda o:-o['q2']); 
for o in out: o['r']=r1.index(o)+1
print("\nrank;prov;tot;cinesi%;+DR/EMC%;altre%;max teorico%")
for o in r1[:20]+[None]+r1[-8:]:
    if o is None: print("..."); continue
    print(o['r'],o['p'],o['tot'],f"{o['q']:.1f}",f"{o['q2']:.1f}",f"{o['qa']:.1f}",f"{o['max']:.1f}")
# robustness: rank under 'all ALTRE chinese' worst case vs 'ALTRE chinese at national ratio'
r2=sorted(out,key=lambda o:-o['max'])
print("\ntop10 caso estremo (tutte le Altre cinesi):",[o['p'] for o in r2[:10]])
print("top10 base:",[o['p'] for o in r1[:10]])
w=csv.writer(open(sys.argv[2],'w',newline='',encoding='utf-8-sig'),delimiter=';')
w.writerow(['Rank','Provincia','Totale immatricolazioni','BYD','MG','Omoda/Jaecoo','Leapmotor','DR/EVO','EMC','Marchi cinesi','Quota marchi cinesi %','Cinesi + DR/EMC','Quota cinesi + DR/EMC %','Altre','Quota Altre %'])
f=lambda x:f"{x:.2f}".replace('.',',')
for o in r1: w.writerow([o['r'],o['p'],o['tot'],o['BYD'],o['MG'],o['OMODA/JAECOO'],o['LEAPMOTOR'],o['DR/EVO'],o['EMC'],o['cn'],f(o['q']),o['cn']+o['it'],f(o['q2']),o['altre'],f(o['qa'])])
w.writerow(['','ITALIA',nat['tot'],nat['BYD'],nat['MG'],nat['OMODA/JAECOO'],nat['LEAPMOTOR'],nat['DR/EVO'],nat['EMC'],nat['cn'],f(nat['q']),nat['cn']+nat['it'],f(nat['q2']),nat['altre'],f(nat['qa'])])
