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
# SAI LỆCH DOANH THU (DIRTY READ / UNREPEATABLE READ)
# ====================================================================
def run_demo_vulnerable():
    print(f"\n{BOLD}{YELLOW}--- PHẦN 1: KHI SỬ DỤNG MỨC CÔ LẬP THẤP (READ UNCOMMITTED) ---{RESET}")
    print("Mô tả: Lễ tân tạo hóa đơn tạm nhưng chưa commit. Quản lý đọc ở mức READ UNCOMMITTED thấy số tiền ảo.")
    
    event_inserted = threading.Event()
    event_rollback = threading.Event()

    def receptionist_thread():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("START TRANSACTION")
        
        print_step("Lễ tân (T1)", "Chèn hóa đơn thanh toán mới của Khách A: 10,000,000 VNĐ (Chưa COMMIT)...", CYAN)
        cursor.execute("""
            INSERT INTO HoaDon (MaDatPhong, TienPhong, TienDichVu, TongTien) 
            VALUES (3, 9000000.00, 1000000.00, 10000000.00)
        """)
        
        event_inserted.set() # Báo cho Quản lý đọc
        time.sleep(2)        # Mô phỏng thời gian chờ thanh toán ngân hàng
        
        print_step("Lễ tân (T1)", "Ngân hàng báo lỗi quẹt thẻ! Hủy giao dịch (ROLLBACK)...", CYAN)
        conn.rollback()
        conn.close()
        
        event_rollback.set()

    def manager_thread():
        event_inserted.wait()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Thiết lập READ UNCOMMITTED để mô phỏng Dirty Read
        cursor.execute("SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
        cursor.execute("START TRANSACTION")
        
        print_step("Quản lý (T2)", "Đang đọc báo cáo tổng doanh thu...", MAGENTA)
        cursor.execute("SELECT SUM(TongTien) AS TotalRevenue FROM HoaDon")
        rev1 = cursor.fetchone()['TotalRevenue'] or 0.0
        print_step("Quản lý (T2)", f"Doanh thu hiển thị (bao gồm tiền chưa commit): {rev1:,.0f} VNĐ", MAGENTA)
        
        event_rollback.wait()
        
        print_step("Quản lý (T2)", "Đọc lại báo cáo doanh thu sau khi giao dịch của lễ tân bị hủy...", MAGENTA)
        cursor.execute("SELECT SUM(TongTien) AS TotalRevenue FROM HoaDon")
        rev2 = cursor.fetchone()['TotalRevenue'] or 0.0
        print_step("Quản lý (T2)", f"Doanh thu hiển thị thực tế: {rev2:,.0f} VNĐ", MAGENTA)
        
        conn.commit()
        conn.close()
        
        if rev1 != rev2:
            print_step("Quản lý (T2)", f"{RED}{BOLD}HẬU QUẢ: Dữ liệu ảo biến mất! Xảy ra hiện tượng DIRTY READ làm sai lệch báo cáo tài chính.{RESET}", MAGENTA)

    t1 = threading.Thread(target=receptionist_thread)
    t2 = threading.Thread(target=manager_thread)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

def run_demo_solved():
    print(f"\n{BOLD}{YELLOW}--- PHẦN 2: KHI SỬ DỤNG MỨC CÔ LẬP AN TOÀN (REPEATABLE READ / MVCC) ---{RESET}")
    print("Mô tả: Sử dụng REPEATABLE READ. Quản lý đọc doanh thu sạch từ Undo Log, không bị ảnh hưởng bởi hóa đơn ảo.")
    
    event_inserted = threading.Event()
    event_rollback = threading.Event()

    def receptionist_thread():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("START TRANSACTION")
        
        print_step("Lễ tân (T1)", "Chèn hóa đơn thanh toán mới của Khách A: 10,000,000 VNĐ (Chưa COMMIT)...", CYAN)
        cursor.execute("""
            INSERT INTO HoaDon (MaDatPhong, TienPhong, TienDichVu, TongTien) 
            VALUES (3, 9000000.00, 1000000.00, 10000000.00)
        """)
        
        event_inserted.set() # Báo cho Quản lý đọc
        time.sleep(2)
        
        print_step("Lễ tân (T1)", "Ngân hàng báo lỗi quẹt thẻ! Hủy giao dịch (ROLLBACK)...", CYAN)
        conn.rollback()
        conn.close()
        
        event_rollback.set()

    def manager_thread():
        event_inserted.wait()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Thiết lập mức cô lập mặc định REPEATABLE READ
        cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        cursor.execute("START TRANSACTION")
        
        print_step("Quản lý (T2)", "Đang đọc báo cáo tổng doanh thu sạch...", MAGENTA)
        cursor.execute("SELECT SUM(TongTien) AS TotalRevenue FROM HoaDon")
        rev1 = cursor.fetchone()['TotalRevenue'] or 0.0
        print_step("Quản lý (T2)", f"Doanh thu hiển thị (chỉ lấy dữ liệu đã commit): {rev1:,.0f} VNĐ", MAGENTA)
        
        event_rollback.wait()
        
        print_step("Quản lý (T2)", "Đọc lại báo cáo doanh thu...", MAGENTA)
        cursor.execute("SELECT SUM(TongTien) AS TotalRevenue FROM HoaDon")
        rev2 = cursor.fetchone()['TotalRevenue'] or 0.0
        print_step("Quản lý (T2)", f"Doanh thu hiển thị: {rev2:,.0f} VNĐ", MAGENTA)
        
        conn.commit()
        conn.close()
        
        if rev1 == rev2:
            print_step("Quản lý (T2)", f"{GREEN}{BOLD}KẾT QUẢ: Báo cáo tài chính ổn định ở mức {rev2:,.0f} VNĐ. MVCC bảo vệ dữ liệu thành công!{RESET}", MAGENTA)


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

    print_header("VẤN ĐỀ 4: SAI LỆCH DOANH THU (DIRTY READ)")
    
    # Chạy kịch bản lỗi
    reset_database()
    run_demo_vulnerable()
    
    # Chạy kịch bản giải pháp
    reset_database()
    run_demo_solved()
