window.__lala = window.__lala || {imgs:{}, log:[], status:'idle'};
window.__lalaRun = async function(items, firstPrefix, nextPrefix){
  const L = window.__lala; L.status='running'; L.items = items.map(x=>x[0]);
  const sleep = ms => new Promise(r=>setTimeout(r,ms));
  const imgs = () => [...document.querySelectorAll('img')].filter(i => (i.alt||'').match(/generated image|oluşturulan görsel|görüntü oluşturuldu/i) && i.naturalWidth>300);
  const lastSrc = () => { const a = imgs(); return a.length ? a[a.length-1].src : null; };
  const stopVisible = () => [...document.querySelectorAll('button')].some(b => /stop/i.test((b.getAttribute('aria-label')||'')+' '+(b.dataset.testid||'')) && b.offsetParent);
  const sendBtn = () => [...document.querySelectorAll('button')].find(b => (b.getAttribute('aria-label')==='Send' || b.dataset.testid==='send-button' || b.id==='composer-submit-button') && !b.disabled);
  for (let k=0; k<items.length; k++){
    const [name, prompt] = items[k];
    if (L.imgs[name]) continue;
    const before = lastSrc();
    const ed = document.querySelector('.ProseMirror[contenteditable="true"]');
    ed.focus(); document.execCommand('selectAll'); document.execCommand('insertText', false, (k===0?firstPrefix:nextPrefix) + (window.__STYLE||'') + (k>0 ? (window.__CHARS||'') : '') + prompt);
    await sleep(800);
    let b = sendBtn(); if(!b){ await sleep(1500); b = sendBtn(); }
    if(!b){ L.log.push(name+': send yok'); L.status='hata: send yok'; return; }
    b.click(); L.log.push(name+': gönderildi '+new Date().toLocaleTimeString());
    const t0 = Date.now(); let got=null, stable=0, prev=null;
    while (Date.now()-t0 < 360000){
      await sleep(5000);
      const s = lastSrc();
      if (s && s!==before && !stopVisible()){
        if (s===prev) stable++; else stable=0;
        prev = s;
        if (stable>=2){ got=s; break; }
      }
    }
    if(!got){
      const msgs=[...document.querySelectorAll('[data-message-author-role="assistant"]')];
      const txt = msgs.length? msgs[msgs.length-1].innerText.slice(0,300):'';
      L.log.push(name+': görsel gelmedi: '+txt); L.status='hata: '+name+': '+txt; return;
    }
    try { const r = await fetch(got, {credentials:'include'}); L.imgs[name] = await r.blob(); L.log.push(name+': tamam '+L.imgs[name].size+' '+L.imgs[name].type+' '+Math.round((Date.now()-t0)/1000)+'sn'); }
    catch(e){ L.log.push(name+': indirme hatası '+e); L.status='hata: indirme '+name; return; }
    await sleep(2000);
  }
  L.status='bitti';
};
window.__lalaZip = async function(fname){
  const L = window.__lala; const enc = new TextEncoder();
  const crcT = new Uint32Array(256).map((_,n)=>{let c=n;for(let k=0;k<8;k++)c=c&1?0xEDB88320^(c>>>1):c>>>1;return c>>>0;});
  const crc = u8 => {let c=0xFFFFFFFF;for(let i=0;i<u8.length;i++)c=crcT[(c^u8[i])&255]^(c>>>8);return (c^0xFFFFFFFF)>>>0;};
  const parts=[], central=[]; let off=0;
  for (const [name, blob] of Object.entries(L.imgs)){
    const ext = (blob.type.split('/')[1]||'png').replace('jpeg','jpg');
    const data = new Uint8Array(await blob.arrayBuffer()); const fn = enc.encode(name+'.'+ext); const c = crc(data);
    const h = new DataView(new ArrayBuffer(30)); h.setUint32(0,0x04034b50,true); h.setUint16(4,20,true); h.setUint32(14,c,true); h.setUint32(18,data.length,true); h.setUint32(22,data.length,true); h.setUint16(26,fn.length,true);
    parts.push(new Uint8Array(h.buffer), fn, data);
    const ch = new DataView(new ArrayBuffer(46)); ch.setUint32(0,0x02014b50,true); ch.setUint16(4,20,true); ch.setUint16(6,20,true); ch.setUint32(16,c,true); ch.setUint32(20,data.length,true); ch.setUint32(24,data.length,true); ch.setUint16(28,fn.length,true); ch.setUint32(42,off,true);
    central.push(new Uint8Array(ch.buffer), fn); off += 30+fn.length+data.length;
  }
  const csize = central.reduce((a,b)=>a+b.length,0); const n = Object.keys(L.imgs).length;
  const e = new DataView(new ArrayBuffer(22)); e.setUint32(0,0x06054b50,true); e.setUint16(8,n,true); e.setUint16(10,n,true); e.setUint32(12,csize,true); e.setUint32(16,off,true);
  const zip = new Blob([...parts, ...central, new Uint8Array(e.buffer)], {type:'application/zip'});
  const a = document.createElement('a'); a.href = URL.createObjectURL(zip); a.download = fname; document.body.appendChild(a); a.click();
  return n+' dosya, '+zip.size+' bayt';
};
'yüklendi';

// ---- Aktarım (24 Kasım 2026): İndirilenler klasörüne erişim yoksa görseller GitHub web yüklemesiyle depoya gider ----
// 1) İkinci ChatGPT sekmesi (B) görsellerini birinci sekmeye (A) yollar:
//    B'de: window.__bc = new BroadcastChannel('lala'); for (const [k,b] of Object.entries(window.__lala.imgs)) window.__bc.postMessage({type:'img', name:k, blob:b});
//    A'da: window.__lala.imgsB = {}; window.__bc = new BroadcastChannel('lala'); window.__bc.onmessage = e => { if (e.data && e.data.type==='img') window.__lala.imgsB[e.data.name] = e.data.blob; };
// 2) A'ya bir düğme ekle; düğmeye GERÇEK tıklama (computer left_click) yap, yoksa açılır pencere engellenir:
//    btn.onclick = () => { window.__gh = window.open('https://github.com/caltun90/lalaanlatiyor-social/upload/main/bolumler/NN-slug/gorseller', 'lalagh'); };
//    Yeni sekme aynı sekme grubuna düşer, Claude in Chrome ile JS çalıştırılabilir.
// 3) GitHub sekmesinde dinleyici:
//    window.__files = {}; window.__uploaded = {};
//    window.addEventListener('message', e => { if (e.origin !== 'https://chatgpt.com' || !e.data || e.data.type!=='img') return; window.__files[e.data.name] = new File([e.data.blob], e.data.name, {type: e.data.blob.type}); });
//    window.__pushFiles = () => { const inp = document.querySelector('input[type=file]'); const dt = new DataTransfer(); for (const [k,f] of Object.entries(window.__files)) { if (window.__uploaded[k]) continue; dt.items.add(f); window.__uploaded[k]=1; } inp.files = dt.files; inp.dispatchEvent(new Event('change', {bubbles:true})); };
// 4) A'da JPEG'e çevirip yolla:
window.__toJpeg = async (blob) => { const bmp = await createImageBitmap(blob); const c = new OffscreenCanvas(bmp.width, bmp.height); c.getContext('2d').drawImage(bmp,0,0); return await c.convertToBlob({type:'image/jpeg', quality:0.92}); };
window.__sent = window.__sent || {};
window.__sendAll = async () => { const all = {...window.__lala.imgs, ...(window.__lala.imgsB||{})}; let n=0; for (const [name, b] of Object.entries(all)) { if (window.__sent[name]) continue; const j = await window.__toJpeg(b); window.__gh.postMessage({type:'img', name: name+'.jpg', blob: j}, 'https://github.com'); window.__sent[name]=j.size; n++; } return n; };
// 5) GitHub sekmesinde __pushFiles(), "Commit summary" alanına yaz, "Commit changes". Commit'ten sonra sayfa depo köküne döner: tekrar yükleme sayfasına git ve 3. adımı yeniden kur.
// ---- Doğrulama (24 Kasım 2026): DOM'daki son görsel her zaman en yeni değil. Eşlemeyi konuşma API'siyle doğrula ----
window.__verify = async (items) => { // items: [[ad, istem], ...] aynı sohbette gönderilenler
  const cid = location.pathname.split('/').pop();
  const tok = (await fetch('/api/auth/session').then(r=>r.json())).accessToken;
  const conv = await fetch('/backend-api/conversation/'+cid, {headers:{Authorization:'Bearer '+tok}}).then(r=>r.json());
  const order=[]; let node = conv.current_node; while (node) { order.unshift(node); node = conv.mapping[node].parent; }
  const out=[]; let lastUser='';
  for (const id of order) { const m = conv.mapping[id].message; if (!m) continue; const parts = (m.content && m.content.parts) || [];
    if (m.author.role==='user') { lastUser = parts.map(p=> typeof p==='string'? p : '').join(' '); continue; }
    for (const p of parts) if (p && typeof p==='object' && p.asset_pointer) out.push({user: lastUser, asset: p.asset_pointer}); }
  const res=[];
  for (const [name, prompt] of items) { const hits = out.filter(o => o.user.includes(prompt.slice(0,60))); if (!hits.length) { res.push(name+': eşleşme yok'); continue; }
    const id = hits[hits.length-1].asset.split('://')[1];
    const j = await fetch('/backend-api/files/download/'+id+'?conversation_id='+cid+'&inline=false', {headers:{Authorization:'Bearer '+tok}}).then(r=>r.json());
    const b = await fetch(j.download_url).then(x=>x.blob()); const run = window.__lala.imgs[name];
    if (!run || run.size !== b.size) { window.__lala.imgs[name] = b; res.push(name+': düzeltildi'); } else res.push(name+': doğru'); }
  return res; };
