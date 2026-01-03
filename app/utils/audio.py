import tempfile

def save_temp_audio(upload_file):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    tmp.write(upload_file.file.read())
    tmp.close()
    return tmp.name
