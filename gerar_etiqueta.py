import requests
import os

def zpl_para_pdf_60x40(arquivo_txt, arquivo_pdf):
    # Verifica se o arquivo de texto existe
    if not os.path.exists(arquivo_txt):
        print(f"Erro: O arquivo '{arquivo_txt}' não foi encontrado.")
        return

    # Lê o código ZPL do arquivo TXT
    with open(arquivo_txt, 'r', encoding='utf-8') as f:
        zpl_data = f.read()

    # Dimensões para a API do Labelary são em polegadas
    # 60mm = ~2.36 polegadas | 40mm = ~1.57 polegadas
    largura_pol = 2.36
    altura_pol = 1.57
    
    # URL da API do Labelary (8dpmm = 203 DPI, padrão de impressoras térmicas)
    url = f'http://api.labelary.com/v1/printers/8dpmm/labels/{largura_pol}x{altura_pol}/0/'
    
    # Pede para a API retornar um arquivo PDF
    headers = {'Accept': 'application/pdf'}
    
    print("Convertendo ZPL para PDF...")
    
    # Envia o código para a API
    response = requests.post(url, headers=headers, data=zpl_data)

    # Verifica se deu certo
    if response.status_code == 200:
        with open(arquivo_pdf, 'wb') as f:
            f.write(response.content)
        print(f"Sucesso! O arquivo visual '{arquivo_pdf}' foi criado.")
    else:
        print(f"Erro na conversão: {response.status_code}")
        print(response.text)

# Executa a função
zpl_para_pdf_60x40("entrada.txt", "etiqueta_final_codigo_de_barras.pdf")