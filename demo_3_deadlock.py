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
MAGENTA = "\033[95m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"

def print_header(title):
    print(f"\n{BOLD}{BLUE}{'='*80}")
    print(f" {title.upper()}")
    print(f"{'='*80}{RESET}")

def print_step(thread_name, message, color=RESET):
    print(f"[{color}{thread_name}{RESET}] {message}")

def execute_sql_file(filepath):
    """Làm sạch và tái lập cơ sở dữ liệu trước khi chạy demo"""
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
    """Reset Database về trạng thái ban đầu để kiểm thử nhất quán"""
    execute_sql_file('sql_scripts/01_schema_index.sql')
    execute_sql_file('sql_scripts/02_trigger.sql')
    execute_sql_file('sql_scripts/03_seed_data.sql')
    execute_sql_file('sql_scripts/04_procedures_core.sql')

# ====================================================================
# KHÓA CHẾT (DEADLOCK)
# ====================================================================
def run_demo_deadlock():
    print(f"\n{BOLD}{YELLOW}--- MÔ PHỎNG HIỆN TƯỢNG DEADLOCK ---{RESET}")
    print("Mô tả: Khách A giữ khóa P101 xin P102. Khách B giữ khóa P102 xin P101. MySQL tự phát hiện và giải phóng.")
    
    barrier = threading.Barrier(2)

    def client_a_thread():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("START TRANSACTION")
        
        print_step("Khách A (T1)", "Khóa phòng P101 (MaPhong=1) thành công...", CYAN)
        cursor.execute("SELECT * FROM Phong WHERE MaPhong = 1 FOR UPDATE")
        
        barrier.wait() # Chờ Khách B khóa xong phòng P102
        time.sleep(0.5)
        
        print_step("Khách A (T1)", "Cố gắng khóa tiếp phòng P102 (MaPhong=2) (Đang bị Khách B giữ khóa)...", CYAN)
        try:
            cursor.execute("SELECT * FROM Phong WHERE MaPhong = 2 FOR UPDATE")
            conn.commit()
            print_step("Khách A (T1)", f"{GREEN}Khóa thành công cả 2 phòng!{RESET}", CYAN)
        except pymysql.MySQLError as e:
            conn.rollback()
            errno = e.args[0]
            if isinstance(errno, int) and errno < 0:
                errno = 65536 + errno
            msg = e.args[1] if len(e.args) > 1 else str(e)
            print_step("Khách A (T1)", f"{RED}Giao dịch thất bại (Mã lỗi {errno}): {msg}{RESET}", CYAN)
        finally:
            conn.close()

    def client_b_thread():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("START TRANSACTION")
        
        print_step("Khách B (T2)", "Khóa phòng P102 (MaPhong=2) thành công...", MAGENTA)
        cursor.execute("SELECT * FROM Phong WHERE MaPhong = 2 FOR UPDATE")
        
        barrier.wait() # Chờ Khách A khóa xong phòng P101
        time.sleep(0.5)
        
        print_step("Khách B (T2)", "Cố gắng khóa tiếp phòng P101 (MaPhong=1) (Đang bị Khách A giữ khóa)...", MAGENTA)
        try:
            cursor.execute("SELECT * FROM Phong WHERE MaPhong = 1 FOR UPDATE")
            conn.commit()
            print_step("Khách B (T2)", f"{GREEN}Khóa thành công cả 2 phòng!{RESET}", MAGENTA)
        except pymysql.MySQLError as e:
            conn.rollback()
            errno = e.args[0]
            if isinstance(errno, int) and errno < 0:
                errno = 65536 + errno
            msg = e.args[1] if len(e.args) > 1 else str(e)
            print_step("Khách B (T2)", f"{RED}Giao dịch thất bại (Mã lỗi {errno}): {msg}{RESET}", MAGENTA)
        finally:
            conn.close()

    t1 = threading.Thread(target=client_a_thread)
    t2 = threading.Thread(target=client_b_thread)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    print(f"\n{GREEN}{BOLD}KẾT LUẬN: Động cơ InnoDB của MySQL phát hiện Deadlock ngay lập tức, tự động hủy bỏ (ROLLBACK) một trong hai giao tác để giải phóng cho luồng kia hoàn thành!{RESET}")


if __name__ == '__main__':
    os.system("") 
    
    # Kiểm tra kết nối DB và chẩn đoán lỗi chi tiết
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
        if isinstance(e, pymysql.MySQLError) and len(e.args) > 0 and e.args[0] == 1049:
            try:
                print(f"\n\033[93m[HỆ THỐNG] Phát hiện database '{Config.DB_NAME}' chưa tồn tại. Đang tự động khởi tạo database...\033[0m")
                conn_init = pymysql.connect(
                    host=Config.DB_HOST,
                    port=Config.DB_PORT,
                    user=Config.DB_USER,
                    password=str(Config.DB_PASSWORD) if Config.DB_PASSWORD is not None else '',
                    charset='utf8mb4',
                    connect_timeout=3
                )
                with conn_init.cursor() as cursor:
                    cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{Config.DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;")
                conn_init.commit()
                conn_init.close()
                print(f"\033[92m[HỆ THỐNG] Đã tạo database '{Config.DB_NAME}' thành công!\033[0m")
            except Exception as init_err:
                print(f"\n\033[91m\033[1m[LỖI KHỞI TẠO DATABASE]\033[0m")
                print(f"\033[91mChi tiết lỗi:\033[0m {init_err}")
                sys.exit(1)
        else:
            print(f"\n\033[91m\033[1m[LỖI KẾT NỐI CƠ SỞ DỮ LIỆU]\033[0m")
            print(f"\033[91mChi tiết lỗi:\033[0m {e}")
            sys.exit(1)

    print_header("VẤN ĐỀ 3: KHÓA CHẾT (DEADLOCK)")
    
    reset_database()
    run_demo_deadlock()
