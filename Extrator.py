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

def extrair_mercadolivre(url, html_text=None):
    """Extrai fotos em alta resolução do Mercado Livre."""
    if not html_text:
        headers = {
            'User-Agent': USER_AGENTS['googlebot'],
            'Accept-Language': 'pt-BR,pt;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        }
        r = requests.get(url, headers=headers, timeout=12, allow_redirects=True)
        if r.status_code != 200:
            # Fallback com Facebookbot
            headers['User-Agent'] = USER_AGENTS['facebook']
            r = requests.get(url, headers=headers, timeout=12, allow_redirects=True)
            if r.status_code != 200:
                return None, [], f"Mercado Livre retornou status HTTP {r.status_code}"
        html_text = r.text

    soup = BeautifulSoup(html_text, 'html.parser')
    
    # Título do anúncio
    titulo = None
    title_el = soup.find('h1') or soup.find('title')
    if title_el:
        titulo = title_el.text.strip().replace(" | MercadoLivre", "").replace(" | Mercado Livre", "").strip()

    imagens = []
    seen_ids = set()

    # Regex para capturar IDs das imagens de anúncio no padrão mlstatic
    # Padrão: 937073-MLB73004859949_112023 ou similar
    matches = re.findall(r'([0-9]{5,}-ML[A-Z][0-9]{7,}_[0-9]{4,})', html_text)
    for pic_id in matches:
        if pic_id not in seen_ids:
            seen_ids.add(pic_id)
            imagens.append({
                'id': pic_id,
                'url': f"https://http2.mlstatic.com/D_NQ_NP_2X_{pic_id}-F.jpg",
                'url_webp': f"https://http2.mlstatic.com/D_NQ_NP_2X_{pic_id}-F.webp",
                'thumb': f"https://http2.mlstatic.com/D_Q_NP_{pic_id}-V.webp"
            })

    # Caso o regex específico não encontre todos, busca em JSON-LD
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            if isinstance(data, dict):
                imgs = data.get('image', [])
                if isinstance(imgs, str):
                    imgs = [imgs]
                for im in imgs:
                    m = re.search(r'([0-9]{5,}-ML[A-Z][0-9]{7,}_[0-9]{4,})', im)
                    if m and m.group(1) not in seen_ids:
                        pic_id = m.group(1)
                        seen_ids.add(pic_id)
                        imagens.append({
                            'id': pic_id,
                            'url': f"https://http2.mlstatic.com/D_NQ_NP_2X_{pic_id}-F.jpg",
                            'url_webp': f"https://http2.mlstatic.com/D_NQ_NP_2X_{pic_id}-F.webp",
                            'thumb': f"https://http2.mlstatic.com/D_Q_NP_{pic_id}-V.webp"
                        })
                    elif not m and im.startswith('http') and im not in [x['url'] for x in imagens]:
                        imagens.append({'id': str(len(imagens)+1), 'url': im, 'thumb': im})
        except Exception:
            pass

    # OpenGraph meta tag
    og_img = soup.find('meta', property='og:image')
    if og_img and og_img.get('content'):
        content = og_img['content']
        m = re.search(r'([0-9]{5,}-ML[A-Z][0-9]{7,}_[0-9]{4,})', content)
        if m and m.group(1) not in seen_ids:
            pic_id = m.group(1)
            seen_ids.add(pic_id)
            imagens.append({
                'id': pic_id,
                'url': f"https://http2.mlstatic.com/D_NQ_NP_2X_{pic_id}-F.jpg",
                'url_webp': f"https://http2.mlstatic.com/D_NQ_NP_2X_{pic_id}-F.webp",
                'thumb': f"https://http2.mlstatic.com/D_Q_NP_{pic_id}-V.webp"
            })

    return titulo, imagens, None


def extrair_generico(url, html_text=None):
    """Extrai imagens de qualquer site geral ou e-commerce."""
    if not html_text:
        headers = {
            'User-Agent': USER_AGENTS['browser'],
            'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
        }
        r = requests.get(url, headers=headers, timeout=12, allow_redirects=True)
        if r.status_code != 200:
            return None, [], f"O site retornou erro HTTP {r.status_code}"
        html_text = r.text

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
        if any(ign in low for ign in ['logo', 'icon', 'pixel', 'avatar', 'badge', 'banner', 'footer', 'header', '.svg']):
            continue

        if full_url not in seen:
            seen.add(full_url)
            imagens.append({'id': str(len(imagens)+1), 'url': full_url, 'thumb': full_url})

    return titulo, imagens, None


def extrair_texto_bruto(texto):
    """Extrai imagens de texto colado (HTML ou lista de URLs)."""
    imagens = []
    seen = set()

    # Shopee susercontent ou cf.shopee
    shopee_matches = re.findall(r'https://(?:down-[a-z0-9\.-]+\.susercontent\.com|cf\.shopee\.com\.br)/file/([a-z0-9_-]+)', texto)
    for sh_id in shopee_matches:
        u = f"https://down-br.img.susercontent.com/file/{sh_id}"
        if u not in seen:
            seen.add(u)
            imagens.append({
                'id': sh_id,
                'url': u,
                'thumb': f"{u}_tn"
            })

    # Mercado Livre mlstatic
    ml_matches = re.findall(r'([0-9]{5,}-ML[A-Z][0-9]{7,}_[0-9]{4,})', texto)
    for ml_id in ml_matches:
        u = f"https://http2.mlstatic.com/D_NQ_NP_2X_{ml_id}-F.jpg"
        if u not in seen:
            seen.add(u)
            imagens.append({
                'id': ml_id,
                'url': u,
                'thumb': f"https://http2.mlstatic.com/D_Q_NP_{ml_id}-V.webp"
            })

    # URLs genéricas de imagem terminando em jpg, png, webp
    gen_matches = re.findall(r'https?://[^\s"\'<>]+\.(?:jpg|jpeg|png|webp)', texto)
    for g_url in gen_matches:
        if g_url not in seen:
            seen.add(g_url)
            imagens.append({'id': str(len(imagens)+1), 'url': g_url, 'thumb': g_url})

    return "Imagens Encontradas no Código", imagens, None


def processar_extracao(entrada):
    """Ponto de entrada: recebe URL ou texto e retorna dicionário com resultados."""
    entrada = entrada.strip()
    if not entrada:
        return {'sucesso': False, 'erro': 'Por favor, insira um link ou código de anúncio.'}

    # Verifica se é uma URL válida
    parsed = urlparse(entrada)
    is_url = bool(parsed.scheme in ('http', 'https') and parsed.netloc)

    if is_url:
        dominio = parsed.netloc.lower()
        if 'mercadolivre.com' in dominio or 'mercadolibre.com' in dominio:
            titulo, imagens, erro = extrair_mercadolivre(entrada)
        elif 'shopee.com' in dominio:
            # Tenta extração via requisição
            titulo, imagens, erro = extrair_generico(entrada)
            if not imagens:
                # Dica explicativa para Shopee
                return {
                    'sucesso': False,
                    'is_shopee_block': True,
                    'erro': 'A Shopee bloqueia conexões automáticas diretas. Use o nosso Atalho/Bookmarklet ou cole o código fonte (Ctrl+U) da página do anúncio!'
                }
        else:
            titulo, imagens, erro = extrair_generico(entrada)
    else:
        # Texto colado / HTML / lista de links
        titulo, imagens, erro = extrair_texto_bruto(entrada)

    if erro:
        return {'sucesso': False, 'erro': erro}

    if not imagens:
        return {'sucesso': False, 'erro': 'Nenhuma imagem foi encontrada no anúncio informado.'}

    return {
        'sucesso': True,
        'titulo': titulo or 'Fotos do Anúncio',
        'total': len(imagens),
        'imagens': imagens
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
