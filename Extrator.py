import re
import io
import json
import zipfile
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin

USER_AGENTS = {
    'googlebot': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
    'browser': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'facebook': 'facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)',
}

def limpar_nome_arquivo(nome):
    """Gera um nome de arquivo seguro a partir do título."""
    if not nome:
        return "fotos_anuncio"
    limpo = re.sub(r'[\\/*?:"<>|]', '', nome)
    limpo = re.sub(r'\s+', '_', limpo).strip('_')
    return limpo[:60] if limpo else "fotos_anuncio"

def normalizar_ml_url(u):
    """Gera URL de alta resolução 2X e thumbnail para Mercado Livre."""
    u_clean = u.split('?')[0]
    m_id = re.search(r'([0-9]{4,}-ML[A-Z][0-9]{6,}(?:_[0-9]{4,})?)', u_clean)
    if m_id:
        pic_id = m_id.group(1)
        ext_match = re.search(r'\.(jpg|jpeg|png|webp)', u_clean, re.IGNORECASE)
        ext = ext_match.group(1).lower() if ext_match else 'jpg'
        hd = f"https://http2.mlstatic.com/D_NQ_NP_2X_{pic_id}-F.{ext}"
        thumb = f"https://http2.mlstatic.com/D_Q_NP_{pic_id}-V.webp"
        return pic_id, hd, thumb
    hd = re.sub(r'D_[A-Z_]*NP_(?:2X_)?', 'D_NQ_NP_2X_', u_clean)
    hd = re.sub(r'-[A-Z]\.(jpg|jpeg|png|webp)', r'-F.\1', hd)
    thumb = re.sub(r'D_[A-Z_]*NP_(?:2X_)?', 'D_Q_NP_', hd)
    thumb = re.sub(r'-[A-Z]\.(jpg|jpeg|png|webp)', r'-V.webp', thumb)
    return hd, hd, thumb

def extrair_mercadolivre(url, html_text=None):
    """Extrai fotos em alta resolução do Mercado Livre."""
    if not html_text:
        headers = {
            'User-Agent': USER_AGENTS['googlebot'],
            'Accept-Language': 'pt-BR,pt;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        }
        try:
            r = requests.get(url, headers=headers, timeout=12, allow_redirects=True)
            if r.status_code != 200:
                headers['User-Agent'] = USER_AGENTS['facebook']
                r = requests.get(url, headers=headers, timeout=12, allow_redirects=True)
                if r.status_code != 200:
                    return None, [], f"Mercado Livre retornou status HTTP {r.status_code}"
            html_text = r.text
        except Exception as e:
            return None, [], f"Erro ao acessar Mercado Livre: {str(e)}"

    cleaned_html = html_text.replace(r'\/', '/').replace(r'\u002F', '/')
    soup = BeautifulSoup(cleaned_html, 'html.parser')
    
    titulo = None
    title_el = soup.find('h1') or soup.find('title')
    if title_el:
        titulo = title_el.text.strip().replace(" | MercadoLivre", "").replace(" | Mercado Livre", "").strip()

    imagens = []
    seen_ids = set()

    # 1. Regex ampla para capturar URLs completas de mlstatic D_
    ml_urls = re.findall(r'https?://(?:http2\.)?mlstatic\.com/D_[^\s"\'<>\)]+', cleaned_html)
    for u in ml_urls:
        pic_id, hd, thumb = normalizar_ml_url(u)
        if pic_id not in seen_ids:
            seen_ids.add(pic_id)
            imagens.append({'id': pic_id, 'url': hd, 'thumb': thumb})

    # 2. Regex específica para IDs de imagens padrão mlstatic
    matches = re.findall(r'([0-9]{4,}-ML[A-Z][0-9]{6,}(?:_[0-9]{4,})?)', cleaned_html)
    for pic_id in matches:
        if pic_id not in seen_ids:
            seen_ids.add(pic_id)
            imagens.append({
                'id': pic_id,
                'url': f"https://http2.mlstatic.com/D_NQ_NP_2X_{pic_id}-F.jpg",
                'thumb': f"https://http2.mlstatic.com/D_Q_NP_{pic_id}-V.webp"
            })

    # 3. JSON-LD Schema
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            if isinstance(data, dict):
                imgs = data.get('image', [])
                if isinstance(imgs, str):
                    imgs = [imgs]
                for im in imgs:
                    m = re.search(r'([0-9]{4,}-ML[A-Z][0-9]{6,}(?:_[0-9]{4,})?)', im)
                    if m and m.group(1) not in seen_ids:
                        pic_id = m.group(1)
                        seen_ids.add(pic_id)
                        imagens.append({
                            'id': pic_id,
                            'url': f"https://http2.mlstatic.com/D_NQ_NP_2X_{pic_id}-F.jpg",
                            'thumb': f"https://http2.mlstatic.com/D_Q_NP_{pic_id}-V.webp"
                        })
                    elif not m and im.startswith('http') and im not in [x['url'] for x in imagens]:
                        imagens.append({'id': str(len(imagens)+1), 'url': im, 'thumb': im})
        except Exception:
            pass

    # 4. OpenGraph meta tag (Capa)
    og_img = soup.find('meta', property='og:image')
    if og_img and og_img.get('content'):
        content = og_img['content']
        m = re.search(r'([0-9]{4,}-ML[A-Z][0-9]{6,}(?:_[0-9]{4,})?)', content)
        if m and m.group(1) not in seen_ids:
            pic_id = m.group(1)
            seen_ids.add(pic_id)
            imagens.append({
                'id': pic_id,
                'url': f"https://http2.mlstatic.com/D_NQ_NP_2X_{pic_id}-F.jpg",
                'thumb': f"https://http2.mlstatic.com/D_Q_NP_{pic_id}-V.webp"
            })
        elif not m and content.startswith('http') and content not in [x['url'] for x in imagens]:
            imagens.append({'id': str(len(imagens)+1), 'url': content, 'thumb': content})

    return titulo, imagens, None


def extrair_generico(url, html_text=None):
    """Extrai imagens de qualquer site geral ou e-commerce."""
    if not html_text:
        headers = {
            'User-Agent': USER_AGENTS['browser'],
            'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
        }
        try:
            r = requests.get(url, headers=headers, timeout=12, allow_redirects=True)
            if r.status_code != 200:
                return None, [], f"O site retornou erro HTTP {r.status_code}"
            html_text = r.text
        except Exception as e:
            return None, [], f"Erro ao acessar site: {str(e)}"

    soup = BeautifulSoup(html_text, 'html.parser')
    
    titulo = None
    title_el = soup.find('title') or soup.find('h1')
    if title_el:
        titulo = title_el.text.strip()

    imagens = []
    seen = set()

    # 1. OpenGraph e Twitter image
    for meta_prop in ['og:image', 'og:image:secure_url', 'twitter:image']:
        for tag in soup.find_all('meta', property=meta_prop):
            u = tag.get('content')
            if u and u.startswith('http') and u not in seen:
                seen.add(u)
                imagens.append({'id': str(len(imagens)+1), 'url': u, 'thumb': u})
        for tag in soup.find_all('meta', attrs={'name': meta_prop}):
            u = tag.get('content')
            if u and u.startswith('http') and u not in seen:
                seen.add(u)
                imagens.append({'id': str(len(imagens)+1), 'url': u, 'thumb': u})

    # 2. JSON-LD Schema
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            if isinstance(data, dict):
                candidates = data.get('image', [])
                if isinstance(candidates, str):
                    candidates = [candidates]
                for c in candidates:
                    img_url = c.get('url') if isinstance(c, dict) else c
                    if isinstance(img_url, str) and img_url.startswith('http') and img_url not in seen:
                        seen.add(img_url)
                        imagens.append({'id': str(len(imagens)+1), 'url': img_url, 'thumb': img_url})
        except Exception:
            pass

    # 3. Tags <img> relevantes
    for img in soup.find_all('img'):
        src = img.get('data-zoom') or img.get('data-large-img') or img.get('data-src') or img.get('src')
        if not src:
            continue
        full_url = urljoin(url, src)
        if not full_url.startswith('http'):
            continue

        # Ignorar logos, rastreadores, ícones pequenos
        low = full_url.lower()
        if any(ign in low for ign in ['logo', 'icon', 'pixel', 'avatar', 'badge', 'banner', 'footer', 'header', '.svg', 'favicon']):
            continue

        if full_url not in seen:
            seen.add(full_url)
            imagens.append({'id': str(len(imagens)+1), 'url': full_url, 'thumb': full_url})

    return titulo, imagens, None


def extrair_texto_bruto(texto):
    """Extrai imagens de texto colado (HTML bruto, código-fonte Ctrl+U ou lista de URLs)."""
    # Desescapa barras e unicode comum em JSON embutido
    cleaned_text = texto.replace(r'\/', '/').replace(r'\u002F', '/')

    # Tenta descobrir o título se for HTML
    titulo = "Fotos Extraídas do Anúncio"
    if '<html' in cleaned_text.lower() or '<head' in cleaned_text.lower() or '<h1' in cleaned_text.lower():
        try:
            soup = BeautifulSoup(cleaned_text[:50000], 'html.parser')
            h1 = soup.find('h1') or soup.find('title')
            if h1 and h1.text.strip():
                t = h1.text.strip()
                t = re.sub(r'\s*[\-–\|].*$', '', t).strip()
                if t:
                    titulo = t[:80]
        except Exception:
            pass

    imagens = []
    seen = set()

    # 1. Mercado Livre mlstatic URLs completas
    ml_urls = re.findall(r'https?://(?:http2\.)?mlstatic\.com/D_[^\s"\'<>\)]+', cleaned_text)
    for u in ml_urls:
        pic_id, hd, thumb = normalizar_ml_url(u)
        if pic_id not in seen:
            seen.add(pic_id)
            imagens.append({'id': pic_id, 'url': hd, 'thumb': thumb})

    # 2. Mercado Livre IDs soltos
    ml_matches = re.findall(r'([0-9]{4,}-ML[A-Z][0-9]{6,}(?:_[0-9]{4,})?)', cleaned_text)
    for ml_id in ml_matches:
        if ml_id not in seen:
            seen.add(ml_id)
            imagens.append({
                'id': ml_id,
                'url': f"https://http2.mlstatic.com/D_NQ_NP_2X_{ml_id}-F.jpg",
                'thumb': f"https://http2.mlstatic.com/D_Q_NP_{ml_id}-V.webp"
            })

    # 3. Shopee susercontent ou cf.shopee
    shopee_matches = re.findall(r'(?:susercontent\.com|cf\.shopee\.com\.br)/file/([a-zA-Z0-9_-]+)', cleaned_text)
    for sh_id in shopee_matches:
        clean_id = re.sub(r'_tn.*$', '', sh_id)
        if clean_id not in seen and len(clean_id) >= 16:
            seen.add(clean_id)
            u = f"https://down-br.img.susercontent.com/file/{clean_id}"
            imagens.append({
                'id': clean_id,
                'url': u,
                'thumb': f"{u}_tn"
            })

    # 4. URLs genéricas de imagem terminando em jpg, png, webp
    seen_urls = {im['url'] for im in imagens}
    gen_matches = re.findall(r'https?://[^\s"\'<>]+\.(?:jpg|jpeg|png|webp)(?:\?[^\s"\'<>]*)?', cleaned_text)
    for g_url in gen_matches:
        low = g_url.lower()
        if any(ign in low for ign in ['logo', 'icon', 'pixel', 'avatar', 'badge', 'banner', 'footer', 'header', '.svg', 'favicon', 'splash', 'assets']):
            continue
        if g_url not in seen_urls and not any(k in g_url for k in seen):
            seen_urls.add(g_url)
            imagens.append({'id': str(len(imagens)+1), 'url': g_url, 'thumb': g_url})

    return titulo, imagens, None


def processar_extracao(entrada):
    """Ponto de entrada: recebe URL ou texto e retorna dicionário com resultados."""
    entrada = entrada.strip()
    if not entrada:
        return {'sucesso': False, 'erro': 'Por favor, insira um link ou código de anúncio.'}

    # Verifica se a entrada já é uma imagem direta (ou contém link direto de imagem)
    low_entrada = entrada.lower()
    is_direct_img = any(low_entrada.endswith(ext) or (ext + '?') in low_entrada for ext in ['.jpg', '.jpeg', '.png', '.webp'])
    if is_direct_img and not ('mercadolivre.com.br/' in low_entrada or 'shopee.com.br/' in low_entrada):
        titulo, imagens, erro = extrair_texto_bruto(entrada)
        if imagens:
            return {
                'sucesso': True,
                'titulo': titulo or 'Imagem Direta',
                'total': len(imagens),
                'imagens': imagens,
                'aviso_bloqueio_marketplace': False,
                'marketplace_nome': None
            }

    # Verifica se é uma URL válida
    parsed = urlparse(entrada)
    is_url = bool(parsed.scheme in ('http', 'https') and parsed.netloc)

    aviso_bloqueio = False
    marketplace_nome = None

    if is_url:
        dominio = parsed.netloc.lower()
        if 'mercadolivre.com' in dominio or 'mercadolibre.com' in dominio:
            marketplace_nome = 'Mercado Livre'
            titulo, imagens, erro = extrair_mercadolivre(entrada)
        elif 'shopee.com' in dominio:
            marketplace_nome = 'Shopee'
            titulo, imagens, erro = extrair_generico(entrada)
        else:
            titulo, imagens, erro = extrair_generico(entrada)
            
        # Detecta se o marketplace bloqueou e só retornou a capa (1 foto)
        if marketplace_nome and len(imagens) <= 1:
            aviso_bloqueio = True
    else:
        # Texto colado / HTML / lista de links
        titulo, imagens, erro = extrair_texto_bruto(entrada)

    if erro and not imagens:
        if marketplace_nome:
            return {
                'sucesso': False,
                'is_marketplace_block': True,
                'marketplace_nome': marketplace_nome,
                'erro': f'O {marketplace_nome} bloqueou o acesso externo automático deste anúncio.'
            }
        return {'sucesso': False, 'erro': erro}

    if not imagens:
        if marketplace_nome:
            return {
                'sucesso': False,
                'is_marketplace_block': True,
                'marketplace_nome': marketplace_nome,
                'erro': f'O {marketplace_nome} bloqueou o acesso externo automático deste anúncio.'
            }
        return {'sucesso': False, 'erro': 'Nenhuma imagem foi encontrada no anúncio informado.'}

    return {
        'sucesso': True,
        'titulo': titulo or 'Fotos do Anúncio',
        'total': len(imagens),
        'imagens': imagens,
        'aviso_bloqueio_marketplace': aviso_bloqueio,
        'marketplace_nome': marketplace_nome
    }


def gerar_zip(lista_urls, titulo="fotos_anuncio"):
    """Baixa as imagens da lista de URLs e compacta em um arquivo .ZIP em memória."""
    zip_buffer = io.BytesIO()
    sucesso_count = 0

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for idx, u in enumerate(lista_urls, 1):
            try:
                headers = {'User-Agent': USER_AGENTS['browser']}
                r = requests.get(u, headers=headers, timeout=12)
                if r.status_code == 200 and len(r.content) > 500:
                    ct = r.headers.get('content-type', '').lower()
                    if 'png' in ct or u.lower().endswith('.png'):
                        ext = 'png'
                    elif 'webp' in ct or u.lower().endswith('.webp'):
                        ext = 'webp'
                    else:
                        ext = 'jpg'

                    filename = f"foto_{idx:02d}.{ext}"
                    zf.writestr(filename, r.content)
                    sucesso_count += 1
            except Exception as e:
                print(f"Erro ao baixar {u}: {e}")

    zip_buffer.seek(0)
    return zip_buffer.getvalue(), sucesso_count
