#!/usr/bin/env python3
"""YouTube API yardimcisi (Lala Anlatiyor). Anahtarlar yalnizca ortam degiskeninden okunur:
YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN. Dosyaya ya da depoya anahtar yazma.

  yt_yukle.py kanal                      -> belirtecin kanalini gosterir
  yt_yukle.py liste                      -> son yuklemeler
  yt_yukle.py video <id>                 -> durum, yayin saati
  yt_yukle.py sil <id>                   -> videoyu siler (yalnizca bu kanalin videosu)
  yt_yukle.py yukle <mp4> <meta.json> [kapak.jpg]
     meta.json: {"snippet": {title, description, tags, categoryId}, "status": {privacyStatus, publishAt, selfDeclaredMadeForKids}}
     Kanal UC-PHvR1Mom6FRRiReVg2USQ degilse yuklemez.
"""
import os, sys, json, subprocess, urllib.parse
import tempfile
S=tempfile.mkdtemp(prefix='yt_')
def curl(args, data=None):
    r=subprocess.run(['curl','-sS','-w','\n%{http_code}']+args,capture_output=True,text=True)
    body,_,code=r.stdout.rpartition('\n')
    return int(code or 0), body, r.stderr
def token():
    code,body,err=curl(['-X','POST','https://oauth2.googleapis.com/token',
        '--data-urlencode','client_id='+os.environ['YT_CLIENT_ID'],'--data-urlencode','client_secret='+os.environ['YT_CLIENT_SECRET'],
        '--data-urlencode','refresh_token='+os.environ['YT_REFRESH_TOKEN'],'--data-urlencode','grant_type=refresh_token'])
    j=json.loads(body) if body.strip().startswith('{') else {}
    if 'access_token' not in j:
        print('TOKEN_ERROR',code,json.dumps({k:v for k,v in j.items()})[:300],err[:200]); sys.exit(4)
    return j['access_token']
def api(tok, method, url, body=None, extra=None):
    a=['-X',method,url,'-H','Authorization: Bearer '+tok]
    if body is not None: a+=['-H','Content-Type: application/json','--data-binary',json.dumps(body,ensure_ascii=False)]
    if extra: a+=extra
    return curl(a)
cmd=sys.argv[1]
tok=token()
if cmd=='kanal':
    c,b,e=api(tok,'GET','https://www.googleapis.com/youtube/v3/channels?part=id,snippet,status&mine=true')
    j=json.loads(b); print(c,[(i['id'],i['snippet']['title'],i.get('status',{}).get('longUploadsStatus')) for i in j.get('items',[])] or b[:400])
elif cmd=='liste':
    c,b,e=api(tok,'GET','https://www.googleapis.com/youtube/v3/channels?part=contentDetails&mine=true')
    up=json.loads(b)['items'][0]['contentDetails']['relatedPlaylists']['uploads']
    c,b,e=api(tok,'GET','https://www.googleapis.com/youtube/v3/playlistItems?part=snippet,status&maxResults=15&playlistId='+up)
    j=json.loads(b)
    for i in j.get('items',[]): print(i['snippet']['resourceId']['videoId'],i['snippet']['publishedAt'],i['status']['privacyStatus'],i['snippet']['title'])
    if not j.get('items'): print(c,b[:300])
elif cmd=='video':
    c,b,e=api(tok,'GET','https://www.googleapis.com/youtube/v3/videos?part=snippet,status,contentDetails,processingDetails&id='+sys.argv[2])
    j=json.loads(b)
    for i in j.get('items',[]):
        print(json.dumps({'id':i['id'],'title':i['snippet']['title'],'channelId':i['snippet']['channelId'],'status':i['status'],'duration':i['contentDetails'].get('duration'),'processing':i.get('processingDetails',{}).get('processingStatus'),'tags':i['snippet'].get('tags'),'cat':i['snippet'].get('categoryId')},ensure_ascii=False,indent=1))
    if not j.get('items'): print(c,b[:400])
elif cmd=='sil':
    c,b,e=api(tok,'GET','https://www.googleapis.com/youtube/v3/videos?part=snippet,status&id='+sys.argv[2])
    it=json.loads(b).get('items',[])
    if not it or it[0]['snippet']['channelId']!='UC-PHvR1Mom6FRRiReVg2USQ': print('SIL_BULUNAMADI',c,b[:200]); sys.exit(8)
    c,b,e=api(tok,'DELETE','https://www.googleapis.com/youtube/v3/videos?id='+sys.argv[2])
    print('SIL',c,b[:300]); sys.exit(0 if c==204 else 9)
elif cmd=='yukle':
    # yukle <video> <meta.json> [kapak.jpg]
    video,meta=sys.argv[2],json.load(open(sys.argv[3],encoding='utf-8'))
    c,b,e=api(tok,'GET','https://www.googleapis.com/youtube/v3/channels?part=id&mine=true')
    ids=[i['id'] for i in json.loads(b).get('items',[])]
    if ids!=['UC-PHvR1Mom6FRRiReVg2USQ']: print('YANLIS_KANAL',ids,b[:200]); sys.exit(5)
    size=os.path.getsize(video)
    r=subprocess.run(['curl','-sS','-D','-','-o',S+'/yt_init.txt','-X','POST',
        'https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status&notifySubscribers=true',
        '-H','Authorization: Bearer '+tok,'-H','Content-Type: application/json; charset=UTF-8','-H','X-Upload-Content-Type: video/mp4','-H',f'X-Upload-Content-Length: {size}',
        '--data-binary',json.dumps(meta,ensure_ascii=False)],capture_output=True,text=True)
    loc=[l.split(':',1)[1].strip() for l in r.stdout.splitlines() if l.lower().startswith('location:')]
    if not loc: print('INIT_ERROR',r.stdout[:300],open(S+'/yt_init.txt').read()[:500]); sys.exit(6)
    c,b,e=curl(['-X','PUT',loc[0],'-H','Content-Type: video/mp4','--data-binary','@'+video,'--max-time','1500'])
    if c not in (200,201): print('UPLOAD_ERROR',c,b[:500],e[:200]); sys.exit(7)
    vid=json.loads(b)['id']; print('VIDEO_ID',vid)
    if len(sys.argv)>4:
        c,b,e=curl(['-X','POST','https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId='+vid,'-H','Authorization: Bearer '+tok,'-H','Content-Type: image/jpeg','--data-binary','@'+sys.argv[4]])
        print('THUMB',c,b[:200] if c!=200 else 'ok')
