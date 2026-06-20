import os
import re
from flask import Flask, render_template, send_from_directory
from flask_socketio import SocketIO
import yt_dlp

try:
    import imageio_ffmpeg
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    ffmpeg_path = None

app = Flask(__name__)
app.config['SECRET_KEY'] = 'snaptube_secret_key'
# Configura o SocketIO para gerenciar a comunicação em tempo real
socketio = SocketIO(app, cors_allowed_origins="*")

BASE_DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), 'downloads')
MP3_DIR = os.path.join(BASE_DOWNLOAD_DIR, 'mp3')
MP4_DIR = os.path.join(BASE_DOWNLOAD_DIR, 'mp4')

os.makedirs(MP3_DIR, exist_ok=True)
os.makedirs(MP4_DIR, exist_ok=True)

# Função auxiliar para limpar códigos de cores ANSI que o yt-dlp envia
def limpar_ansi(texto):
    return re.sub(r'\x1b\[[0-9;]*m', '', texto)

# Função de gancho (hook) que o yt_dlp chama a cada bloco baixado
def progress_hook(d):
    if d['status'] == 'downloading':
        # Extrai e limpa os dados brutos de progresso
        porcentagem = limpar_ansi(d.get('_percent_str', '0.0%')).strip()
        velocidade = limpar_ansi(d.get('_speed_str', '0B/s')).strip()
        tempo_restante = limpar_ansi(d.get('_eta_str', '00:00')).strip()
        
        # Converte a string "45.2%" em um número para a barra de progresso do HTML
        try:
            p_num = float(porcentagem.replace('%', ''))
        except:
            p_num = 0

        # Envia os dados instantaneamente para o navegador via WebSocket
        socketio.emit('progresso_download', {
            'porcentagem': porcentagem,
            'p_num': p_num,
            'velocidade': velocidade,
            'tempo': tempo_restante,
            'status': 'Baixando...'
        })
    elif d['status'] == 'finished':
        socketio.emit('progresso_download', {
            'porcentagem': '100%',
            'p_num': 100,
            'velocidade': '0B/s',
            'tempo': '00:00',
            'status': 'Finalizando/Convertendo arquivo...'
        })

@app.route('/')
def index():
    musicas = os.listdir(MP3_DIR)
    videos = os.listdir(MP4_DIR)
    return render_template('index.html', musicas=musicas, videos=videos)

# Rotas para servir os arquivos para o Player e para Download
@app.route('/midia/mp3/<filename>')
def servir_mp3(filename):
    return send_from_directory(MP3_DIR, filename)

@app.route('/midia/mp4/<filename>')
def servir_mp4(filename):
    return send_from_directory(MP4_DIR, filename)

# Evento do WebSocket que recebe a ordem de download do formulário
@socketio.on('iniciar_download_evento')
def handle_download(data):
    url = data.get('url')
    opcao = data.get('opcao')
    
    ydl_opts = {
        'progress_hooks': [progress_hook],
    }
    
    if ffmpeg_path:
        ydl_opts['ffmpeg_location'] = ffmpeg_path

    if opcao == '1': # MP3
        ydl_opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': os.path.join(MP3_DIR, '%(title)s.%(ext)s'),
        })
    else: # MP4
        ydl_opts.update({
            'format': 'bestvideo+bestaudio/best',
            'outtmpl': os.path.join(MP4_DIR, '%(title)s.%(ext)s'),
            'merge_output_format': 'mp4',
        })

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        socketio.emit('download_concluido', {'sucesso': True, 'msg': 'Download concluído com sucesso!'})
    except Exception as e:
        socketio.emit('download_concluido', {'sucesso': False, 'msg': f'Erro: {str(e)}'})

if __name__ == '__main__':
    # Importante: para WebSockets, rodamos com o socketio e não com o app.run tradicional
    socketio.run(app, debug=True)