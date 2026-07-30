# 🏷️ Gerador de Etiquetas ZPL → PDF

Aplicativo web que converte arquivos ZPL em PDF para dois formatos de etiqueta:

- 📦 **Produto** — 60 × 40 mm
- 📫 **Volume** — 100 × 150 mm

---

## 🚀 Como usar localmente

1. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```

2. Inicie o servidor:
   ```bash
   python app.py
   ```

3. Acesse **http://localhost:5000** no navegador.

Ou simplesmente dê dois cliques em **`Abrir Gerador de Etiquetas.bat`**.

---

## ☁️ Deploy no Render (hospedagem gratuita)

### Passo 1 — Criar repositório no GitHub

1. Acesse [github.com](https://github.com) e faça login
2. Clique em **New repository**
3. Dê um nome (ex: `gerador-etiquetas`)
4. Deixe como **Public** e clique em **Create repository**

### Passo 2 — Enviar o código para o GitHub

Abra o terminal (PowerShell) na pasta do projeto e execute:

```powershell
git init
git add .
git commit -m "Primeiro commit"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/gerador-etiquetas.git
git push -u origin main
```

> Substitua `SEU_USUARIO` pelo seu nome de usuário do GitHub.

### Passo 3 — Publicar no Render

1. Acesse [render.com](https://render.com) e faça login com sua conta GitHub
2. Clique em **New → Web Service**
3. Selecione o repositório `gerador-etiquetas`
4. Configure:
   - **Name:** `gerador-etiquetas` (ou qualquer nome)
   - **Runtime:** `Python`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
5. Clique em **Deploy Web Service**

Após alguns minutos, o Render fornecerá uma URL pública como:
```
https://gerador-etiquetas.onrender.com
```

---

## 📁 Estrutura do projeto

```
├── app.py                         ← Servidor Flask
├── Produto.py                     ← Lógica etiqueta 60×40mm
├── Volume.py                      ← Lógica etiqueta 100×150mm
├── requirements.txt               ← Dependências Python
├── Procfile                       ← Configuração para Render/Heroku
├── .gitignore                     ← Arquivos ignorados pelo Git
├── Abrir Gerador de Etiquetas.bat ← Atalho local (Windows)
├── templates/
│   └── index.html                 ← Interface web
└── static/
    └── style.css                  ← Estilos
```

---

## 🛠️ Tecnologias

- **Python / Flask** — servidor web
- **fpdf2** — geração de PDF
- **Labelary API** — renderização do ZPL
- **HTML / CSS / JavaScript** — interface

---

## ⚠️ Observações

- O arquivo `.bat` é apenas para uso local no Windows e **não** deve ser enviado ao servidor.
- Os PDFs gerados ficam salvos temporariamente no servidor — considere uma solução de armazenamento (ex: AWS S3) para produção em larga escala.
