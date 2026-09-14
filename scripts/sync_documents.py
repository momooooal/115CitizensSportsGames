#!/usr/bin/env python3
"""Keep every official schedule attachment readable and searchable in the site."""
import argparse,io,json,hashlib,time,unicodedata,logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
from pypdf import PdfReader
import pdfplumber
from sync_data import ROOT,official_url,key

def main():
    logging.getLogger('pdfminer').setLevel(logging.ERROR)
    logging.getLogger('pypdf').setLevel(logging.ERROR)
    p=argparse.ArgumentParser();p.add_argument('--offline-manifest',type=Path);p.add_argument('--force',action='store_true');p.add_argument('--output',type=Path,default=ROOT/'site/data');args=p.parse_args()
    output=args.output;snapshot=json.loads((output/'snapshot.json').read_text());dest=output/'documents.json'
    previous=json.loads(dest.read_text()) if dest.exists() else None
    if previous and not args.force and not args.offline_manifest:
        same_urls={d['url'] for d in previous['documents']}=={d['url'] for d in snapshot['documents']}
        age=(datetime.now(timezone.utc)-datetime.fromisoformat(previous['checked_at'])).total_seconds()
        if same_urls and age<86400:print('Schedule PDFs already checked today');return
    manifest=json.loads(args.offline_manifest.read_text()) if args.offline_manifest else {}
    mapping={official_url(url):args.offline_manifest.parent/(name+'.html') for name,url in manifest.items()} if manifest else {}
    def read(doc):
        if mapping:
            raw=mapping[doc['url']].read_bytes();observed=datetime.fromtimestamp(mapping[doc['url']].stat().st_mtime,timezone.utc).isoformat()
        else:
            for attempt in range(3):
                try:
                    with urlopen(Request(doc['url'],headers={'User-Agent':'KaohsiungSport115/1.0 (official schedule PDFs)'}),timeout=45) as response:
                        raw=response.read(25_000_001)
                    if len(raw)>25_000_000:raise ValueError('PDF exceeds size limit')
                    if not raw.startswith(b'%PDF'):raise ValueError('Source did not return a PDF')
                    time.sleep(.2);break
                except Exception:
                    if attempt==2:raise
                    time.sleep(1+attempt)
            observed=datetime.now(timezone.utc).isoformat()
        reader=PdfReader(io.BytesIO(raw))
        pages=[unicodedata.normalize('NFKC',page.extract_text() or '') for page in reader.pages]
        tables=[]
        # Table geometry is useful for date cells spanning several match rows.
        if doc['sport_id'] in ('210','213','209','214','205','134','211') and '資格' not in doc['title']:
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                for index,page in enumerate(pdf.pages):
                    tables.append({'page':index+1,'tables':page.extract_tables()})
        return {**doc,'sha256':hashlib.sha256(raw).hexdigest(),'checked_at':observed,'page_count':len(pages),'pages':pages,'tables':tables,'searchable':any(p.strip() for p in pages)}
    with ThreadPoolExecutor(max_workers=3) as pool:documents=list(pool.map(read,snapshot['documents']))
    data={'schema_version':1,'checked_at':max(d['checked_at'] for d in documents),'documents':documents}
    raw=json.dumps(data,ensure_ascii=False,separators=(',',':'))
    for name,content in [('documents.json',raw),('documents.js','window.SPORT115_DOCUMENTS = '+raw.replace('</','<\\/')+';\n')]:
        tmp=output/(name+'.tmp');tmp.write_text(content,encoding='utf-8');tmp.replace(output/name)
    print(json.dumps({'documents':len(documents),'pages':sum(d['page_count'] for d in documents),'searchable':sum(d['searchable'] for d in documents)},ensure_ascii=False))

if __name__=='__main__':main()
