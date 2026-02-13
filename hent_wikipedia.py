import requests
import json
import time
import re
from pathlib import Path

class WikipediaKnowledgeBase:
    def __init__(self, output_dir="knowledge_base"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.endpoints = {
            'en': 'https://en.wikipedia.org/w/api.php',
            'no': 'https://no.wikipedia.org/w/api.php'
        }
        
    def fetch_article(self, title, lang='en'):
        """
        Henter artikkel med full tekst, seksjoner og referanser
        """
        params = {
            'action': 'query',
            'format': 'json',
            'titles': title,
            'prop': 'extracts|info|categories',
            'explaintext': True,  # Ren tekst uten HTML
            'exsectionformat': 'plain',
            'inprop': 'url',
            'cllimit': 'max',
            'redirects': 1
        }
        
        try:
            response = requests.get(
                self.endpoints[lang], 
                params=params,
                headers={'User-Agent': 'EyeControlBot/1.0 (educational project)'}
            )
            response.raise_for_status()
            data = response.json()
            
            pages = data['query']['pages']
            page_id = list(pages.keys())[0]
            
            if page_id == '-1':
                print(f"Artikkel ikke funnet: {title} ({lang})")
                return None
                
            page = pages[page_id]
            
            return {
                'title': page['title'],
                'language': lang,
                'url': page['fullurl'],
                'extract': page.get('extract', ''),
                'categories': [cat['title'] for cat in page.get('categories', [])],
                'length': len(page.get('extract', ''))
            }
            
        except Exception as e:
            print(f"Feil ved henting av {title}: {e}")
            return None
    
    def chunk_text(self, text, chunk_size=1000, overlap=200):
        """
        Deler tekst i chunks for RAG
        """
        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
        chunks = []
        current_chunk = ""
        
        for para in paragraphs:
            if len(current_chunk) + len(para) < chunk_size:
                current_chunk += para + "\n\n"
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = para + "\n\n"
                
        if current_chunk:
            chunks.append(current_chunk.strip())
            
        return chunks
    
    def save_article(self, article_data):
        """
        Lagrer artikkel som JSON med chunks
        """
        if not article_data:
            return
            
        safe_title = re.sub(r'[^\w\s-]', '', article_data['title']).replace(' ', '_')
        filename = f"{article_data['language']}_{safe_title}.json"
        filepath = self.output_dir / filename
        
        # Lag chunks for RAG
        chunks = self.chunk_text(article_data['extract'])
        
        structured_data = {
            'metadata': {
                'title': article_data['title'],
                'language': article_data['language'],
                'source_url': article_data['url'],
                'categories': article_data['categories'],
                'total_length': article_data['length'],
                'chunk_count': len(chunks)
            },
            'chunks': [
                {
                    'id': f"{safe_title}_{i}",
                    'text': chunk,
                    'index': i
                }
                for i, chunk in enumerate(chunks)
            ],
            'full_text': article_data['extract']  # Behold full tekst som backup
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(structured_data, f, ensure_ascii=False, indent=2)
            
        print(f"Lagret: {filename} ({len(chunks)} chunks)")
        
    def build_knowledge_base(self, articles_config):
        """
        Hovedfunksjon - henter alle definerte artikler
        articles_config: liste med dicts {'title': '...', 'lang': '...'}
        """
        for item in articles_config:
            print(f"Henter: {item['title']} ({item['lang']})...")
            
            data = self.fetch_article(item['title'], item['lang'])
            
            if data:
                self.save_article(data)
                
            # Rate limiting - vær snill mot API-et
            time.sleep(1)
            
        print(f"\nFerdig! Lagret i: {self.output_dir.absolute()}")

# Konfigurasjon - legg til artikler her
ARTICLES_TO_FETCH = [
    # Kjerneartikler - Engelsk (mer detaljert)
    {'title': 'Eye tracking', 'lang': 'en'},
    {'title': 'Gaze', 'lang': 'en'},
    {'title': 'Augmentative and alternative communication', 'lang': 'en'},
    {'title': 'Assistive technology', 'lang': 'en'},
    {'title': 'Computer accessibility', 'lang': 'en'},
    {'title': 'Brain–computer interface', 'lang': 'en'},
    {'title': 'Locked-in syndrome', 'lang': 'en'},
    {'title': 'Amyotrophic lateral sclerosis', 'lang': 'en'},
    {'title': 'Stephen Hawking', 'lang': 'en'},
    
    # Norske artikler (for lokal kontekst)
    {'title': 'Øyesporing', 'lang': 'no'},
    {'title': 'Hjelpemiddel', 'lang': 'no'},
    {'title': 'Universell utforming', 'lang': 'no'},
    {'title': 'Amyotrofisk lateralsklerose', 'lang': 'no'},
    {'title': 'Menneske-maskin-interaksjon', 'lang': 'no'}
]

if __name__ == "__main__":
    kb = WikipediaKnowledgeBase()
    kb.build_knowledge_base(ARTICLES_TO_FETCH)