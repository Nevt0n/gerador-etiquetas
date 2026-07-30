import sys
import os
import json
import uuid
import queue
import threading
from flask import Flask, render_template, request, Response, stream_with_context, send_file

# Garante que o diretório atual seja o da pasta do projeto
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import Produto
import Volume

app = Flask(__name__)

# Armazenamento temporário em memória: { job_id: conteudo_txt }
jobs = {}


# ── Upload do arquivo ──────────────────────────────────────────────────────────
@app.route('/upload', methods=['POST'])
def upload():
    """Recebe o arquivo TXT, guarda em memória e retorna um job_id."""
    arquivo = request.files.get('arquivo')
    if not arquivo:
        return json.dumps({'erro': 'Nenhum arquivo enviado'}), 400, {'Content-Type': 'application/json'}

    try:
        conteudo = arquivo.read().decode('utf-8')
    except Exception:
        return json.dumps({'erro': 'Erro ao ler o arquivo. Certifique-se de que é UTF-8.'}), 400, {'Content-Type': 'application/json'}

    job_id = str(uuid.uuid4())
    jobs[job_id] = conteudo

    return json.dumps({'job_id': job_id}), 200, {'Content-Type': 'application/json'}


# ── Stream de progresso via SSE ────────────────────────────────────────────────
def gerar_stream(conteudo_txt, modo):
    """Gera eventos SSE com o progresso do processamento."""
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
                caminho_pdf = os.path.join(BASE_DIR, nome_arquivo)
                with open(caminho_pdf, 'wb') as f:
                    f.write(pdf_bytes)
                q.put(json.dumps({
                    "tipo": "concluido",
                    "msg": f"PDF gerado com {total} pagina(s)!",
                    "arquivo": nome_arquivo,
                    "total": total
                }))
            else:
                q.put(json.dumps({"tipo": "erro", "msg": "Nenhuma etiqueta foi gerada. Verifique o arquivo TXT."}))
        except Exception as e:
            q.put(json.dumps({"tipo": "erro", "msg": f"Erro interno: {str(e)}"}))
        finally:
            q.put(None)

    thread = threading.Thread(target=processar, daemon=True)
    thread.start()

    while True:
        item = q.get()
        if item is None:
            break
        yield f"data: {item}\n\n"


@app.route('/gerar/<modo>')
def gerar(modo):
    if modo not in ('produto', 'volume'):
        return "Modo invalido", 400

    job_id = request.args.get('job_id', '')
    if not job_id or job_id not in jobs:
        return "Job nao encontrado. Faca o upload do arquivo novamente.", 400

    conteudo_txt = jobs[job_id]

    return Response(
        stream_with_context(gerar_stream(conteudo_txt, modo)),
        content_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


# ── Download do PDF ────────────────────────────────────────────────────────────
@app.route('/download/<nome_arquivo>')
def download(nome_arquivo):
    if not nome_arquivo.endswith('.pdf') or '/' in nome_arquivo or '\\' in nome_arquivo:
        return "Arquivo invalido", 400

    caminho = os.path.join(BASE_DIR, nome_arquivo)
    if not os.path.exists(caminho):
        return "Arquivo nao encontrado", 404

    return send_file(caminho, as_attachment=True, download_name=nome_arquivo)


# ── Página principal ───────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    print("=" * 50)
    print("  Gerador de Etiquetas ZPL -> PDF")
    print(f"  Acesse: http://localhost:{port}")
    print("=" * 50)
    app.run(debug=False, host='0.0.0.0', port=port)
