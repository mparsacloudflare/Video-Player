from flask import Flask, render_template_string, request, jsonify
from flask_socketio import SocketIO, emit
import os
import uuid

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'secret!')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# پوشه ذخیره فایل‌ها در Railway (از دایرکتوری موقت استفاده میکنیم)
UPLOAD_FOLDER = '/tmp/uploads'  # Railway از /tmp پشتیبانی میکنه
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ذخیره وضعیت فعلی
current_media = {
    'type': None,
    'src': None,
    'filename': None
}

# ==================== HTML های داخلی ====================

INDEX_HTML = '''
<!DOCTYPE html>
<html dir="rtl" lang="fa">
<head>
    <meta charset="UTF-8">
    <title>پخش لحظه‌ای</title>
    <script src="https://cdn.socket.io/4.5.0/socket.io.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Tahoma; background: #1a1a2e; color: white; text-align: center; padding: 20px; min-height: 100vh; display: flex; flex-direction: column; justify-content: center; }
        h1 { font-size: 2.5rem; margin-bottom: 10px; background: linear-gradient(45deg, #00d4ff, #00ff88); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .status { color: #00ff88; font-size: 18px; margin-bottom: 20px; }
        #media-container { margin: 20px auto; max-width: 90%; }
        video, audio { max-width: 100%; max-height: 80vh; border-radius: 15px; box-shadow: 0 0 50px rgba(0,255,255,0.2); }
        iframe { width: 100%; max-width: 800px; height: 500px; border-radius: 15px; border: none; }
        .empty-state { color: #666; font-size: 20px; padding: 50px; }
        .footer { margin-top: 30px; color: #444; font-size: 14px; }
    </style>
</head>
<body>
    <h1>🎬 پخش زنده</h1>
    <p class="status">🟢 منتظر محتوای جدید از ادمین...</p>
    <div id="media-container">
        <div class="empty-state">📺 هیچ محتوایی در حال پخش نیست</div>
    </div>
    <div class="footer">🔹 مدیریت محتوا از پنل ادمین</div>

    <script>
        const socket = io();
        const container = document.getElementById('media-container');

        socket.on('update_media', function(data) {
            if (data.type === 'video') {
                container.innerHTML = `<video controls autoplay><source src="${data.src}"></video>`;
            } else if (data.type === 'audio') {
                container.innerHTML = `<audio controls autoplay><source src="${data.src}"></audio>`;
            } else if (data.type === 'link') {
                container.innerHTML = `<iframe src="${data.src}" allowfullscreen></iframe>`;
            } else {
                container.innerHTML = '<div class="empty-state">📺 هیچ محتوایی در حال پخش نیست</div>';
            }
        });

        fetch('/get_current_media')
            .then(res => res.json())
            .then(data => {
                if (data.src) {
                    socket.emit('update_media', data);
                }
            });
    </script>
</body>
</html>
'''

ADMIN_HTML = '''
<!DOCTYPE html>
<html dir="rtl" lang="fa">
<head>
    <meta charset="UTF-8">
    <title>پنل مدیریت</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Tahoma; background: #0f0f1a; color: white; padding: 20px; }
        .container { max-width: 700px; margin: auto; background: #1e1e3a; padding: 30px; border-radius: 20px; box-shadow: 0 0 50px rgba(0,212,255,0.1); }
        h2 { color: #00d4ff; margin-bottom: 20px; font-size: 2rem; text-align: center; }
        .current { background: #00ff8822; padding: 15px; border-radius: 10px; border-right: 4px solid #00ff88; margin-bottom: 20px; }
        .box { background: #2a2a4a; padding: 20px; border-radius: 15px; margin: 20px 0; }
        input, button, input[type="file"] { 
            width: 100%; padding: 14px; margin: 10px 0; border-radius: 10px; border: none;
            font-size: 16px; background: #3a3a5a; color: white;
        }
        input::placeholder { color: #888; }
        button { background: linear-gradient(45deg, #00d4ff, #00ff88); color: #000; font-weight: bold; cursor: pointer; transition: 0.3s; }
        button:hover { transform: scale(1.02); box-shadow: 0 0 30px rgba(0,255,136,0.3); }
        .btn-danger { background: linear-gradient(45deg, #ff4444, #ff6b6b); color: white; }
        .btn-danger:hover { box-shadow: 0 0 30px rgba(255,68,68,0.3); }
        .label { color: #00d4ff; font-size: 14px; }
        #current-label { color: #00ff88; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <h2>🔧 پنل مدیریت</h2>
        
        <div class="current">
            📺 محتوای فعلی: <span id="current-label">هیچ</span>
        </div>

        <div class="box">
            <h3 style="color:#00d4ff;">📤 آپلود فایل</h3>
            <form id="uploadForm" enctype="multipart/form-data">
                <input type="file" name="file" accept="video/*,audio/*" required>
                <button type="submit">🚀 آپلود و پخش</button>
            </form>
        </div>

        <div class="box">
            <h3 style="color:#00d4ff;">🔗 ارسال لینک</h3>
            <form id="linkForm">
                <input type="url" name="link" placeholder="https://example.com/video.mp4" required>
                <button type="submit">📡 ارسال لینک</button>
            </form>
        </div>

        <div class="box">
            <h3 style="color:#ff4444;">🗑️ حذف محتوا</h3>
            <button onclick="clearMedia()" class="btn-danger">❌ پاک کردن محتوای فعلی</button>
        </div>
        
        <div style="text-align:center;margin-top:20px;color:#666;font-size:14px;">
            🔹 تمام کاربران آنلاین محتوا را لحظه‌ای می‌بینند
        </div>
    </div>

    <script>
        document.getElementById('uploadForm').onsubmit = async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            const res = await fetch('/upload', { method: 'POST', body: formData });
            const data = await res.json();
            if (data.success) {
                alert('✅ فایل با موفقیت آپلود شد!');
                updateStatus(data.media);
            } else {
                alert('❌ خطا: ' + (data.error || 'مشخص نیست'));
            }
        };

        document.getElementById('linkForm').onsubmit = async (e) => {
            e.preventDefault();
            const link = e.target.link.value;
            const res = await fetch('/set_link', { 
                method: 'POST', 
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({link})
            });
            const data = await res.json();
            if (data.success) {
                alert('✅ لینک ارسال شد!');
                updateStatus(data.media);
            } else {
                alert('❌ خطا: ' + (data.error || 'مشخص نیست'));
            }
        };

        async function clearMedia() {
            if (!confirm('میخوای محتوا رو پاک کنی؟')) return;
            const res = await fetch('/clear', { method: 'POST' });
            const data = await res.json();
            if (data.success) {
                alert('🗑️ پاک شد!');
                document.getElementById('current-label').textContent = 'هیچ';
            }
        }

        function updateStatus(media) {
            if (media && media.src) {
                const label = media.filename || media.src;
                document.getElementById('current-label').textContent = label.length > 50 ? label.substring(0,50)+'...' : label;
            }
        }

        fetch('/get_current_media')
            .then(res => res.json())
            .then(data => {
                if (data.src) updateStatus(data);
            });
    </script>
</body>
</html>
'''

# ==================== مسیرها ====================

@app.route('/')
def index():
    return render_template_string(INDEX_HTML)

@app.route('/admin')
def admin():
    return render_template_string(ADMIN_HTML)

@app.route('/get_current_media')
def get_current_media():
    return jsonify(current_media)

@app.route('/upload', methods=['POST'])
def upload_file():
    global current_media
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'فایلی وجود ندارد'})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'فایل انتخاب نشده'})
    
    # ذخیره فایل با نام یکتا
    ext = file.filename.split('.')[-1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)
    
    # تشخیص نوع
    if ext in ['mp4', 'mov', 'avi', 'mkv', 'webm']:
        media_type = 'video'
    elif ext in ['mp3', 'wav', 'ogg', 'm4a']:
        media_type = 'audio'
    else:
        media_type = 'link'
    
    # به‌روزرسانی
    current_media = {
        'type': media_type,
        'src': f'/uploads/{filename}',
        'filename': file.filename
    }
    
    # ارسال به همه کاربران
    socketio.emit('update_media', current_media)
    
    return jsonify({'success': True, 'media': current_media})

@app.route('/set_link', methods=['POST'])
def set_link():
    global current_media
    data = request.get_json()
    link = data.get('link', '').strip()
    
    if not link:
        return jsonify({'success': False, 'error': 'لینک معتبر نیست'})
    
    current_media = {
        'type': 'link',
        'src': link,
        'filename': link[:50] + '...' if len(link) > 50 else link
    }
    
    socketio.emit('update_media', current_media)
    return jsonify({'success': True, 'media': current_media})

@app.route('/clear', methods=['POST'])
def clear_media():
    global current_media
    current_media = {'type': None, 'src': None, 'filename': None}
    socketio.emit('update_media', current_media)
    return jsonify({'success': True})

# ==================== اجرا ====================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("""
    ╔═══════════════════════════════════════╗
    ║   🚀 سرور با موفقیت روشن شد!        ║
    ║   📱 در حال اجرا روی Railway         ║
    ╚═══════════════════════════════════════╝
    """)
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
