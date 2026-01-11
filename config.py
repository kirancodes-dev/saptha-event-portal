import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'SapthaHack_Enterprise_Key_2025'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///event_portal.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Email Settings (Update with your App Password)
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = 'sapthhack@gmail.com'
    MAIL_PASSWORD = 'uukg zspf mtho voiy'  # Keep your app password here
    MAIL_DEFAULT_SENDER = ('SapthaHack Portal', 'sapthhack@gmail.com')
    
    # Upload Paths (For future posters/certificates)
    UPLOAD_FOLDER = os.path.join(os.getcwd(), 'static/uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB Max File Size