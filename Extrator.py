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
    """Extrai fotos em alta resolução estritamente da galeria do anúncio do Mercado Livre."""
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

    # REGRA ESTRITA: Extrair APENAS da galeria do anúncio (.ui-pdp-gallery)
    ml_gallery = soup.find(class_=re.compile(r'ui-pdp-gallery'))
    if ml_gallery:
        for img in ml_gallery.find_all('img'):
            src = img.get('data-zoom') or img.get('src') or img.get('data-src') or ''
            if src and 'mlstatic.com/D_' in src:
                pic_id, hd, thumb = normalizar_ml_url(src)
                if pic_id not in seen_ids:
                    seen_ids.add(pic_id)
                    imagens.append({'id': pic_id, 'url': hd, 'thumb': thumb})

    # Se não achou na tag .ui-pdp-gallery, busca no Schema JSON-LD de Product (estritamente do produto)
    if not imagens:
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and data.get('@type') == 'Product':
                    imgs = data.get('image', [])
                    if isinstance(imgs, str):
                        imgs = [imgs]
                    for im in imgs:
                        if isinstance(im, str) and 'mlstatic.com/D_' in im:
                            pic_id, hd, thumb = normalizar_ml_url(im)
                            if pic_id not in seen_ids:
                                seen_ids.add(pic_id)
                                imagens.append({'id': pic_id, 'url': hd, 'thumb': thumb})
            except Exception:
                pass

    # Se ainda assim não achou e tem og:image, pega apenas a capa
    if not imagens:
        og_img = soup.find('meta', property='og:image')
        if og_img and og_img.get('content'):
            content = og_img['content']
            if 'mlstatic.com/D_' in content:
                pic_id, hd, thumb = normalizar_ml_url(content)
                if pic_id not in seen_ids:
                    seen_ids.add(pic_id)
                    imagens.append({'id': pic_id, 'url': hd, 'thumb': thumb})

    return titulo, imagens, None


def extrair_generico(url, html_text=None):
    """Extrai imagens estritamente da galeria principal de qualquer site ou e-commerce."""
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

    # 1. Procura primeiro Schema JSON-LD de Product (padrão confiável para produto específico)
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string)
            if isinstance(data, dict) and data.get('@type') == 'Product':
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

    # Se achou fotos no Schema do produto, retorna imediatamente sem pegar carrosséis da página
    if imagens:
        return titulo, imagens, None

    # 2. Descarta blocos de produtos relacionados, footer, avaliações
    for unwanted in soup.find_all(class_=re.compile(r'recommendation|carousel|related|similar|reviews|comments|footer|header|banner|sidebar')):
        if not unwanted or not getattr(unwanted, 'attrs', None):
            continue
        classes = unwanted.attrs.get('class', [])
        class_str = " ".join(classes) if isinstance(classes, list) else str(classes)
        if 'product-gallery' not in class_str and 'woocommerce-product-gallery' not in class_str:
            try:
                unwanted.decompose()
            except Exception:
                pass

    # 3. Procura container de galeria do produto
    gallery_container = soup.find(class_=re.compile(r'woocommerce-product-gallery|product-gallery|product-images|product-photos|photoswipe'))
    target = gallery_container or soup

    for img in target.find_all('img'):
        src = img.get('data-zoom') or img.get('data-large-img') or img.get('data-src') or img.get('src')
        if not src:
            continue
        full_url = urljoin(url, src)
        if not full_url.startswith('http'):
            continue

        low = full_url.lower()
        if any(ign in low for ign in ['logo', 'icon', 'pixel', 'avatar', 'badge', 'banner', 'footer', 'header', '.svg', 'favicon']):
            continue

        if full_url not in seen:
            seen.add(full_url)
            imagens.append({'id': str(len(imagens)+1), 'url': full_url, 'thumb': full_url})

    # 4. OpenGraph como fallback se nenhuma foto da galeria foi achada
    if not imagens:
        for meta_prop in ['og:image', 'og:image:secure_url', 'twitter:image']:
            for tag in soup.find_all('meta', property=meta_prop):
                u = tag.get('content')
                if u and u.startswith('http') and u not in seen:
                    seen.add(u)
                    imagens.append({'id': str(len(imagens)+1), 'url': u, 'thumb': u})

    return titulo, imagens, None


def extrair_texto_bruto(texto):
    """Extrai imagens estritamente da galeria do anúncio (HTML bruto, Ctrl+U ou links)."""
    cleaned_text = texto.replace(r'\/', '/').replace(r'\u002F', '/')
    imagens = []
    seen = set()
    titulo = "Fotos do Anúncio"

    is_html = ('<html' in cleaned_text.lower() or '<head' in cleaned_text.lower() or '<div' in cleaned_text.lower() or '<body' in cleaned_text.lower())

    if is_html:
        soup = BeautifulSoup(cleaned_text, 'html.parser')
        
        # 1. Título do anúncio
        h1 = soup.find('h1') or soup.find('title')
        if h1 and h1.text.strip():
            t = re.sub(r'\s*[\-–\|].*$', '', h1.text.strip()).strip()
            if t: titulo = t[:80]

        # 2. Remove blocos que sabidamente NÃO pertencem ao anúncio
        # (mas NUNCA remove elementos que estejam dentro da galeria do anúncio)
        for unwanted in soup.find_all(class_=re.compile(r'recommendation|related|similar|reviews|comments|buyer|ratings|footer|header|banner|sidebar|cross-sells|upsells')):
            if not unwanted or not getattr(unwanted, 'attrs', None):
                continue
            # Se o elemento estiver dentro da galeria do anúncio, preserva
            if unwanted.find_parent(class_=re.compile(r'ui-pdp-gallery|product-briefing|product-gallery|woocommerce-product-gallery')):
                continue
            classes = unwanted.attrs.get('class', [])
            class_str = " ".join(classes) if isinstance(classes, list) else str(classes)
            if 'ui-pdp-gallery' not in class_str and 'product-briefing' not in class_str and 'product-gallery' not in class_str and 'product-images' not in class_str:
                try:
                    unwanted.decompose()
                except Exception:
                    pass

        # 3. REGRA ESTRITA POR MARKETPLACE
        # Mercado Livre: busca exclusivamente dentro de .ui-pdp-gallery
        ml_gallery = soup.find(class_=re.compile(r'ui-pdp-gallery'))
        if ml_gallery:
            for img in ml_gallery.find_all('img'):
                src = img.get('data-zoom') or img.get('src') or img.get('data-src') or ''
                if src and 'mlstatic.com/D_' in src:
                    pic_id, hd, thumb = normalizar_ml_url(src)
                    if pic_id not in seen:
                        seen.add(pic_id)
                        imagens.append({'id': pic_id, 'url': hd, 'thumb': thumb})

        # Shopee: busca exclusivamente dentro de .product-briefing
        shopee_gallery = soup.find(class_=re.compile(r'product-briefing|page-product__detail'))
        if shopee_gallery and not imagens:
            for img in shopee_gallery.find_all('img'):
                src = img.get('src') or img.get('data-src') or ''
                if src and ('susercontent.com/file/' in src or 'cf.shopee.com.br/file/' in src):
                    m = re.search(r'(?:susercontent\.com|cf\.shopee\.com\.br)/file/([a-zA-Z0-9_-]+)', src)
                    if m:
                        clean_id = re.sub(r'_tn.*$', '', m.group(1))
                        if len(clean_id) >= 16 and clean_id not in seen:
                            seen.add(clean_id)
                            u = f"https://down-br.img.susercontent.com/file/{clean_id}"
                            imagens.append({'id': clean_id, 'url': u, 'thumb': f"{u}_tn"})

        # Lojas gerais: busca na galeria do produto
        if not imagens:
            gen_gallery = soup.find(class_=re.compile(r'woocommerce-product-gallery|product-gallery|product-images|product-photos|photoswipe'))
            if gen_gallery:
                for img in gen_gallery.find_all('img'):
                    src = img.get('data-zoom') or img.get('data-large-img') or img.get('src') or img.get('data-src') or ''
                    if src and src.startswith('http') and not any(ign in src.lower() for ign in ['logo', 'icon', 'pixel', 'avatar', '.svg']):
                        if src not in seen:
                            seen.add(src)
                            imagens.append({'id': str(len(imagens)+1), 'url': src, 'thumb': src})

        # 4. Schema JSON-LD de Product (apenas fotos do produto anunciado)
        if not imagens:
            for s in soup.find_all('script', type='application/ld+json'):
                try:
                    data = json.loads(s.string)
                    if isinstance(data, dict) and data.get('@type') == 'Product':
                        imgs = data.get('image', [])
                        if isinstance(imgs, str): imgs = [imgs]
                        for im in imgs:
                            if isinstance(im, str):
                                if 'mlstatic.com/D_' in im:
                                    pic_id, hd, thumb = normalizar_ml_url(im)
                                    if pic_id not in seen:
                                        seen.add(pic_id)
                                        imagens.append({'id': pic_id, 'url': hd, 'thumb': thumb})
                                elif 'susercontent.com/file/' in im:
                                    m = re.search(r'susercontent\.com/file/([a-zA-Z0-9_-]+)', im)
                                    if m:
                                        clean_id = re.sub(r'_tn.*$', '', m.group(1))
                                        if clean_id not in seen:
                                            seen.add(clean_id)
                                            u = f"https://down-br.img.susercontent.com/file/{clean_id}"
                                            imagens.append({'id': clean_id, 'url': u, 'thumb': f"{u}_tn"})
                                elif im.startswith('http') and im not in seen:
                                    seen.add(im)
                                    imagens.append({'id': str(len(imagens)+1), 'url': im, 'thumb': im})
                except Exception:
                    pass

        # 5. Estado JSON interno específico do anúncio (Shopee item.images ou ML gallery.pictures)
        if not imagens:
            m_shopee_state = re.search(r'"item"\s*:\s*\{[^\}]*"images"\s*:\s*\[([^\]]+)\]', cleaned_text)
            if m_shopee_state:
                hashes = re.findall(r'"([a-zA-Z0-9_-]{16,})"', m_shopee_state.group(1))
                for h in hashes:
                    if h not in seen:
                        seen.add(h)
                        u = f"https://down-br.img.susercontent.com/file/{h}"
                        imagens.append({'id': h, 'url': u, 'thumb': f"{u}_tn"})

            m_ml_state = re.search(r'"gallery"\s*:\s*\{[^\}]*"pictures"\s*:\s*\[([^\]]+)\]', cleaned_text)
            if m_ml_state:
                urls = re.findall(r'"(https?://http2\.mlstatic\.com/D_[^"]+)"', m_ml_state.group(1))
                for u in urls:
                    pic_id, hd, thumb = normalizar_ml_url(u)
                    if pic_id not in seen:
                        seen.add(pic_id)
                        imagens.append({'id': pic_id, 'url': hd, 'thumb': thumb})

    else:
        # Texto colado que NÃO é HTML (ex: lista direta de URLs)
        for u in re.findall(r'https?://(?:http2\.)?mlstatic\.com/D_[^\s"\'<>\)]+', cleaned_text):
            pic_id, hd, thumb = normalizar_ml_url(u)
            if pic_id not in seen:
                seen.add(pic_id)
                imagens.append({'id': pic_id, 'url': hd, 'thumb': thumb})

        for u in re.findall(r'(?:susercontent\.com|cf\.shopee\.com\.br)/file/([a-zA-Z0-9_-]+)', cleaned_text):
            clean_id = re.sub(r'_tn.*$', '', u)
            if len(clean_id) >= 16 and clean_id not in seen:
                seen.add(clean_id)
                img_url = f"https://down-br.img.susercontent.com/file/{clean_id}"
                imagens.append({'id': clean_id, 'url': img_url, 'thumb': f"{img_url}_tn"})

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
