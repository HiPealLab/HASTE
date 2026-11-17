import sys,re,statistics as st
P=sys.argv[1]
cfgs="lif_10 lif_64x10 lif_64x64x10 izh_10 izh_64x10 izh_64x64x10 hh_10 hh_64x10 hh_64x64x10 lif_cnn".split()
print("cfg acc mean_cyc lat_cyc_ms xt_mean_ms xt_min xt_max ovh_ns_mean ovh_min ovh_max | WNS LUT FF BRAM DSP Ptot")
for c in cfgs:
    L=open(f"{P}/{c}/uart_{c}.log",errors="replace").read()
    lat=L.split(">>> PHASE LATENCY START")[1].split("SUMMARY")[0]
    cyc=[int(x) for x in re.findall(r"^IMG \d+ .*CYCLES (\d+)",lat,re.M)]
    t=[(int(a),int(b)) for a,b in re.findall(r"^TIME \d+ XTIME_NS (\d+) HW_NS (\d+)",lat,re.M)]
    xt=[a/1e6 for a,b in t]; ov=[a-b for a,b in t]
    s=re.search(r"correct=(\d+)",L).group(1)
    S=open(f"{P}/{c}/reports/summary.txt").read()
    w=re.search(r"WNS=([\d.-]+)",S).group(1); u=re.search(r"SliceLUTs=(\d+) FF=(\d+) BRAM_tiles=([\d.]+) DSP=(\d+)",S).groups(); p=re.search(r"total=([\d.]+)W",S).group(1)
    print(c,int(s)/10,len(cyc),len(t),round(st.mean(cyc)),round(st.mean(cyc)/5e4,3),round(st.mean(xt),3),round(min(xt),3),round(max(xt),3),round(st.mean(ov)),min(ov),max(ov),"|",w,*u,p)
