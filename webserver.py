from flask import Flask, request, send_from_directory, render_template, flash, redirect, session
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename
import os
import subprocess
import zipfile

UPLOAD_FOLDER = 'uploads/'
OUTPUT_FOLDER = 'output/'
ALLOWED_EXTENSIONS = {'wav'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = "supersecretkey"  # for flashing messages

socketio = SocketIO(app)

# Create directories if they don't exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

clients = {}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@socketio.on('client_connected')
def handle_client_connect(data):
    session['sid'] = request.sid

@socketio.on('disconnect')
def handle_client_disconnect():
    clients.pop(request.sid, None)

@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files['file']

    if file.filename == '':
        flash('No selected file')
        return redirect(request.url)
        
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
            
        base_name = os.path.splitext(filename)[0]

        # Process with demucs
        cmd = [
            "python3", "-m", "demucs", "--int24", "-n", "htdemucs_6s",
            "-d", "cuda", filepath, "-o", "output/"
        ]
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in process.stdout:
            if "%" in line and "[" in line and "]" in line:
                socketio.emit('status', {'message': line.strip()}, room=session.get('sid'))  # Use the sid from Flask's session

        process.communicate()
            
        
        # Create ZIP
        output_folder = os.path.join("output", "htdemucs_6s", base_name)
        zip_filename = os.path.join(app.config['UPLOAD_FOLDER'], f"{base_name}.zip")
        with zipfile.ZipFile(zip_filename, 'w') as zipf:
            for root, _, files in os.walk(output_folder):
                for file in files:
                    file_path = os.path.join(root, file)
                    zipf.write(file_path, os.path.relpath(file_path, output_folder))
            
        zip_filename = f"{base_name}.zip"
        socketio.emit('status', {'message': 'Processing complete!', 'filename': zip_filename}, room=session.get('sid'))
        return "File processed", 200
    else:
        flash('Allowed file types are .wav')
        return redirect(request.url)


@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    # Send the file for download
    response = send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)
    
    # After sending the file for download, clear the contents of the directories
    clear_directory(app.config['UPLOAD_FOLDER'])
    clear_directory(OUTPUT_FOLDER)

    return response
@app.route('/')
def index():
    return render_template('index.html')
def clear_directory(directory):
    for root, dirs, files in os.walk(directory, topdown=False):
        for name in files:
            os.remove(os.path.join(root, name))
        for name in dirs:
            os.rmdir(os.path.join(root, name))
if __name__ == "__main__":
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)