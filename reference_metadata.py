"""Verify bibliographic identifiers against Crossref, never fuzzy-match a title alone."""
import json
import re
from urllib.parse import urlencode


def verified_reference_papers(references, http):
    candidates=[]
    for ref in references:
        match=re.search(r'\b(Science|Nature|Physical Review Letters)\s+(\d+)\s*\((\d{4})\)\s*([A-Za-z0-9]+)',ref['text'])
        if match:
            candidates.append((ref,match.groups()))
    # Prioritize complete Science identifiers; this is a bibliography excerpt, never a claim of sole prize attribution.
    candidates.sort(key=lambda pair:pair[1][0]!='Science')
    verified=[]
    for ref,(journal,volume,year,article) in candidates[:3]:
        url='https://api.crossref.org/works?'+urlencode({'query.bibliographic':ref['text'],'rows':3,
            'select':'DOI,title,author,published,container-title,volume,page,article-number,type'})
        try:
            data=json.loads(http(url,timeout=4,limit=1024*1024,headers={'User-Agent':'LocalLineBot/1.0'}))
            for item in data.get('message',{}).get('items',[]):
                date=item.get('published',{}).get('date-parts',[[]])[0]
                identifiers={str(item.get(key,'')).split('-')[0] for key in ('article-number','page')}
                containers=item.get('container-title',[])
                if (item.get('type')!='journal-article' or str(item.get('volume'))!=volume
                    or not date or str(date[0])!=year or article not in identifiers
                    or journal.casefold() not in [str(c).casefold() for c in containers]):
                    continue
                doi=item.get('DOI','')
                title=item.get('title',[])
                if not title or not re.fullmatch(r'10\.\d{4,9}/[^\s<>"\x00-\x1f]+',doi):
                    continue
                if any(p['doi']==doi for p in verified):
                    break
                authors=[a.get('name') or ' '.join(filter(None,[a.get('given'),a.get('family')])) for a in item.get('author',[])[:3]]
                verified.append(dict(title=str(title[0])[:400],authors=', '.join(authors) or '作者見來源書目',
                    year=year,journal=journal,doi=doi,reference=ref['number'],url=url))
                break
        except Exception:
            continue
        if len(verified)==2:
            break
    return verified
