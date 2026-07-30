import sys
import requests
import io
import os
import time
import re
from fpdf import FPDF

def limpar_imagem_zpl(codigo_zpl):
    # Mantemos a limpeza por segurança, caso haja logotipos pesados
    codigo_limpo = re.sub(r'\^GF[^^~]*', '', codigo_zpl)
    codigo_limpo = re.sub(r'~DG[^^~]*', '', codigo_limpo)
    return codigo_limpo

def _processar_zpl(conteudo, largura_mm, altura_mm, largura_pol, altura_pol, img_w, img_h, callback=None):
    """Núcleo do processamento: recebe conteúdo ZPL como string e retorna bytes do PDF."""
    etiquetas_zpl = re.findall(r'\^XA.*?\^XZ', conteudo, flags=re.DOTALL)
    total_modelos = len(etiquetas_zpl)

    if callback:
        callback('info', f'Encontrados {total_modelos} modelo(s) de etiqueta.')

    if total_modelos == 0:
        return None, 0

    pdf = FPDF(orientation='P', unit='mm', format=(largura_mm, altura_mm))
    pdf.set_margins(1, 1, 1)

    url = f'http://api.labelary.com/v1/printers/8dpmm/labels/{largura_pol}x{altura_pol}/0/'
    headers = {'Accept': 'image/png'}
    total_paginas_geradas = 0

    for i, zpl in enumerate(etiquetas_zpl, 1):
        match_qtd = re.search(r'\^PQ(\d+)', zpl)
        quantidade = int(match_qtd.group(1)) if match_qtd else 1
        zpl_leve = limpar_imagem_zpl(zpl)
        zpl_para_api = re.sub(r'\^PQ\d+', '^PQ1', zpl_leve)
        try:
            if callback:
                callback('progress', f'Processando {i}/{total_modelos} ({quantidade} cópia(s))...')
            response = requests.post(url, headers=headers, data=zpl_para_api.encode('utf-8'))
            if response.status_code == 200:
                for _ in range(quantidade):
                    pdf.add_page()
                    pdf.image(io.BytesIO(response.content), x=1, y=1, w=img_w, h=img_h)
                    total_paginas_geradas += 1
            else:
                if callback:
                    callback('error', f'Erro HTTP {response.status_code} no modelo {i}')
            time.sleep(0.5)
        except Exception as e:
            if callback:
                callback('error', str(e))

    if total_paginas_geradas > 0:
        try:
            pdf_bytes = pdf.output()
        except Exception:
            pdf_bytes = pdf.output(dest='S').encode('latin-1')
        return pdf_bytes, total_paginas_geradas
    return None, 0


def gerar_pdf_bytes(conteudo_txt, callback=None):
    """Importável pelo Flask: recebe conteúdo ZPL como string, retorna bytes do PDF (100x150mm)."""
    return _processar_zpl(
        conteudo=conteudo_txt,
        largura_mm=100, altura_mm=150,
        largura_pol=3.94, altura_pol=5.91,
        img_w=98, img_h=148,
        callback=callback
    )


def gerar_pdf_multiplas_etiquetas(arquivo_txt, arquivo_pdf):
    if not os.path.exists(arquivo_txt):
        print(f"Erro: O arquivo '{arquivo_txt}' não foi encontrado.")
        return

    with open(arquivo_txt, 'r', encoding='utf-8') as f:
        conteudo = f.read()

    def log(tipo, msg):
        print(msg)

    pdf_bytes, total = gerar_pdf_bytes(conteudo, callback=log)

    if pdf_bytes:
        with open(arquivo_pdf, 'wb') as f:
            f.write(pdf_bytes)
        print(f"\nVITÓRIA! O seu PDF completo possui {total} página(s) e foi salvo em '{arquivo_pdf}'.")
    else:
        print("\nFalha geral na geração das etiquetas.")


# Executa o código (modo standalone)
if __name__ == '__main__':
    if len(sys.argv) >= 2:
        arquivo_entrada = sys.argv[1]
    else:
        arquivo_entrada = input("Digite o nome do arquivo TXT de entrada (ex: meu_arquivo.txt): ").strip()

    if len(sys.argv) >= 3:
        arquivo_saida = sys.argv[2]
    else:
        base = os.path.splitext(os.path.basename(arquivo_entrada))[0]
        arquivo_saida = f"{base}_volume.pdf"

    gerar_pdf_multiplas_etiquetas(arquivo_entrada, arquivo_saida)

