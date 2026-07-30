import sys
import os
import json
import queue
import threading
from flask import Flask, render_template, request, Response, stream_with_context

# Garante que o diretório atual seja o da pasta do projeto
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import Produto
import Volume

app = Flask(__name__)


def gerar_stream(conteudo_txt, modo):
    """Gera eventos SSE (Server-Sent Events) com o progresso do processamento."""
    q = queue.Queue()

    def callback(tipo, msg):
        q.put(json.dumps({"tipo": tipo, "msg": msg}))

    def processar():
        try:
            if modo == 'produto':
                pdf_bytes, total = Produto.gerar_pdf_bytes(conteudo_txt, callback=callback)
                nome_arquivo = "etiquetas_produto_60x40.pdf"
            else:
                pdf_bytes, total = Volume.gerar_pdf_bytes(conteudo_txt, callback=callback)
                nome_arquivo = "etiquetas_volume_100x150.pdf"

            if pdf_bytes and total > 0:
                # Salva o PDF gerado na pasta do projeto
                caminho_pdf = os.path.join(BASE_DIR, nome_arquivo)
                with open(caminho_pdf, 'wb') as f:
                    f.write(pdf_bytes)
                q.put(json.dumps({
                    "tipo": "concluido",
                    "msg": f"PDF gerado com {total} página(s)!",
                    "arquivo": nome_arquivo,
                    "total": total
                }))
            else:
                q.put(json.dumps({"tipo": "erro", "msg": "Nenhuma etiqueta foi gerada. Verifique o arquivo TXT."}))
        except Exception as e:
            q.put(json.dumps({"tipo": "erro", "msg": f"Erro interno: {str(e)}"}))
        finally:
            q.put(None)  # Sinaliza fim

    thread = threading.Thread(target=processar, daemon=True)
    thread.start()

    while True:
        item = q.get()
        if item is None:
            break
        yield f"data: {item}\n\n"


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/gerar/<modo>')
def gerar(modo):
    if modo not in ('produto', 'volume'):
        return "Modo inválido", 400

    conteudo_b64 = request.args.get('conteudo', '')
    if not conteudo_b64:
        return "Conteúdo vazio", 400

    import base64
    try:
        conteudo_txt = base64.b64decode(conteudo_b64).decode('utf-8')
    except Exception:
        return "Erro ao decodificar conteúdo", 400

    return Response(
        stream_with_context(gerar_stream(conteudo_txt, modo)),
        content_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


@app.route('/download/<nome_arquivo>')
def download(nome_arquivo):
    from flask import send_file
    # Segurança: apenas PDFs gerados por esta aplicação
    if not nome_arquivo.endswith('.pdf') or '/' in nome_arquivo or '\\' in nome_arquivo:
        return "Arquivo inválido", 400

    caminho = os.path.join(BASE_DIR, nome_arquivo)
    if not os.path.exists(caminho):
        return "Arquivo não encontrado", 404

    return send_file(caminho, as_attachment=True, download_name=nome_arquivo)


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    print("=" * 50)
    print("  Gerador de Etiquetas ZPL -> PDF")
    print(f"  Acesse: http://localhost:{port}")
    print("=" * 50)
    app.run(debug=False, host='0.0.0.0', port=port)
