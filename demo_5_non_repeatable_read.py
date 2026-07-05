import os
import sys
import time
import threading
import pymysql
from pymysql.cursors import DictCursor

# Thêm thư mục hiện tại vào PYTHONPATH để import được các module của app
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from config import Config
from app.database import get_db_connection

# Khởi tạo màu sắc hiển thị trên Terminal để dễ theo dõi
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"

def print_header(title):
    print(f"\n{BOLD}{BLUE}{'='*80}")
    print(f" {title.upper()}")
    print(f"{'='*80}{RESET}")

def print_step(thread_name, message, color=RESET):
    print(f"[{color}{thread_name}{RESET}] {message}")

def execute_sql_file(filepath):
    conn = get_db_connection()
    if conn is None:
        print(f"{RED}Không thể kết nối Database để chạy Demo!{RESET}")
        sys.exit(1)
    
    with open(filepath, 'r', encoding='utf-8') as f:
        sql_content = f.read()

    with conn.cursor() as cursor:
        statements = []
        current_statement = []
        in_delimiter_block = False
        
        lines = sql_content.split('\n')
        for line in lines:
            line_no_comment = line.split('--')[0] if '--' in line else line
            cleaned_line = line_no_comment.strip()
            if not cleaned_line:
                continue
            
            if cleaned_line.startswith('DELIMITER //'):
                in_delimiter_block = True
                continue
            elif cleaned_line.startswith('DELIMITER ;'):
                in_delimiter_block = False
                continue
            
            if in_delimiter_block:
                if cleaned_line.endswith('//'):
                    current_statement.append(cleaned_line[:-2])
                    statements.append(' '.join(current_statement))
                    current_statement = []
                else:
                    current_statement.append(line)
            else:
                if cleaned_line.endswith(';'):
                    current_statement.append(cleaned_line)
                    statements.append(' '.join(current_statement))
                    current_statement = []
                else:
                    current_statement.append(line)
        
        for statement in statements:
            if statement.strip():
                try:
                    cursor.execute(statement)
                except Exception as e:
                    pass
        conn.commit()
    conn.close()

def reset_database():
    execute_sql_file('sql_scripts/01_schema_index.sql')
    execute_sql_file('sql_scripts/02_trigger.sql')
    execute_sql_file('sql_scripts/03_seed_data.sql')
    execute_sql_file('sql_scripts/04_procedures_core.sql')

# ====================================================================
# DEMO NON-REPEATABLE READ
# ====================================================================
def run_demo_non_repeatable_read(isolation_level_name, isolation_level_sql):
    print(f"\n{BOLD}{YELLOW}--- CHẠY DEMO VỚI ISOLATION LEVEL: {isolation_level_name} ---{RESET}")
    
    barrier = threading.Barrier(2)
    shared_data = {}

    def reader_thread():
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Thiết lập Isolation Level cho Transaction này
        cursor.execute(f"SET TRANSACTION ISOLATION LEVEL {isolation_level_sql}")
        cursor.execute("START TRANSACTION")
        
        # Lần đọc 1: Đọc giá phòng của loại phòng Standard (MaLoaiPhong = 1)
        cursor.execute("SELECT GiaTieuChuan FROM LoaiPhong WHERE MaLoaiPhong = 1")
        price_1 = float(cursor.fetchone()["GiaTieuChuan"])
        print_step("Reader (T1)", f"Lần đọc 1: Giá phòng Standard là {price_1:,.0f} VNĐ", CYAN)
        shared_data["price_1"] = price_1

        # Chờ Writer thực hiện cập nhật và commit
        barrier.wait()
        
        # Chờ 0.5s để đảm bảo Writer đã commit xong xuôi
        time.sleep(0.5)
        
        # Lần đọc 2: Đọc lại giá phòng Standard lần nữa
        cursor.execute("SELECT GiaTieuChuan FROM LoaiPhong WHERE MaLoaiPhong = 1")
        price_2 = float(cursor.fetchone()["GiaTieuChuan"])
        print_step("Reader (T1)", f"Lần đọc 2: Giá phòng Standard là {price_2:,.0f} VNĐ", CYAN)
        shared_data["price_2"] = price_2
        
        cursor.execute("COMMIT")
        conn.close()

    def writer_thread():
        # Đợi Reader đọc xong lần 1
        barrier.wait()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("START TRANSACTION")
        
        # Cập nhật giá phòng lên 900,000 VNĐ
        print_step("Writer (T2)", "Cập nhật giá phòng Standard từ 800,000 lên 900,000 VNĐ và COMMIT...", MAGENTA)
        cursor.execute("UPDATE LoaiPhong SET GiaTieuChuan = 900000.00 WHERE MaLoaiPhong = 1")
        cursor.execute("COMMIT")
        conn.close()

    t1 = threading.Thread(target=reader_thread)
    t2 = threading.Thread(target=writer_thread)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Nhận xét kết quả
    if shared_data["price_1"] == shared_data["price_2"]:
        print(f"{GREEN}KẾT QUẢ: KHÔNG xảy ra Non-repeatable Read. Dữ liệu nhất quán giữa các lần đọc!{RESET}")
    else:
        print(f"{RED}KẾT QUẢ: XẢY RA Non-repeatable Read! Dữ liệu thay đổi từ {shared_data['price_1']:,.0f} thành {shared_data['price_2']:,.0f} VNĐ.{RESET}")

if __name__ == '__main__':
    os.system("") 
    
    # Kiểm tra kết nối DB
    try:
        conn = pymysql.connect(
            host=Config.DB_HOST,
            port=Config.DB_PORT,
            user=Config.DB_USER,
            password=str(Config.DB_PASSWORD) if Config.DB_PASSWORD is not None else '',
            db=Config.DB_NAME,
            charset='utf8mb4',
            connect_timeout=3
        )
        conn.close()
    except Exception as e:
        print(f"\n\033[91m[LỖI KẾT NỐI CƠ SỞ DỮ LIỆU] Vui lòng kiểm tra lại cấu hình DB.{RESET}")
        sys.exit(1)

    print_header("VẤN ĐỀ 5: ĐỌC KHÔNG LẶP LẠI (NON-REPEATABLE READ)")
    
    # 1. Demo lỗi xảy ra dưới mức cô lập READ COMMITTED
    reset_database()
    run_demo_non_repeatable_read("READ COMMITTED (Bị lỗi)", "READ COMMITTED")
    
    # 2. Demo cách giải quyết bằng mức cô lập mặc định REPEATABLE READ của main
    reset_database()
    run_demo_non_repeatable_read("REPEATABLE READ (Đã giải quyết trên main)", "REPEATABLE READ")
