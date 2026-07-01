import pymysql
from pymysql.cursors import DictCursor
from config import Config

def get_db_connection():
    try:
        connection = pymysql.connect(
            host=Config.DB_HOST,
            port=Config.DB_PORT,
            user=Config.DB_USER,
            password=str(Config.DB_PASSWORD) if Config.DB_PASSWORD is not None else '',
            db=Config.DB_NAME,
            charset='utf8mb4',
            cursorclass=DictCursor,
            connect_timeout=3
        )
        # ❌ [DEMO-UNSOLVED] Ép READ UNCOMMITTED → cho phép đọc dữ liệu chưa COMMIT (Dirty Read)
        with connection.cursor() as cursor:
            cursor.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
        return connection
    except Exception as e:
        # Trả về None nếu chưa cài đặt/khởi động Database, routes sẽ dùng mock data để hiển thị giao diện
        return None

