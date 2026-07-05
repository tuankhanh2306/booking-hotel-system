import os
import sys
import time
import threading
import pymysql
from pymysql.cursors import DictCursor
from datetime import date, timedelta

# Khởi tạo ngày động
TARGET_DATE = date.today() + timedelta(days=10)
TARGET_DATE_STR = TARGET_DATE.strftime('%Y-%m-%d')
NEW_CHECKIN_STR = (TARGET_DATE - timedelta(days=1)).strftime('%Y-%m-%d')
NEW_CHECKOUT_STR = (TARGET_DATE + timedelta(days=2)).strftime('%Y-%m-%d')

# Thêm thư mục hiện tại vào PYTHONPATH để import được các module của app
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from config import Config
from app.database import get_db_connection
from app.error_codes import get_error_message

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
# ĐỌC BÓNG MA (PHANTOM READ)
# ====================================================================
def run_demo_vulnerable():
    print(f"\n{BOLD}{YELLOW}--- PHẦN 1: KHI CHƯA CÓ PHƯƠNG ÁN NGĂN CHẶN BÓNG MA (VULNERABLE) ---{RESET}")
    print(f"Mô tả: Lễ tân dùng REPEATABLE READ đếm phòng cọc ngày {TARGET_DATE_STR}. Khách hàng C chèn mới. Lễ tân đếm lại thấy tăng (Phantom Read).")
    
    event_read_1 = threading.Event()
    event_insert = threading.Event()

    def receptionist_thread():
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Sử dụng READ COMMITTED để mô phỏng rõ Phantom Read (hoặc REPEATABLE READ nhưng không dùng khóa)
        cursor.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
        cursor.execute("START TRANSACTION")
        
        print_step("Lễ tân (T1)", f"Lần 1: Đếm tổng số đơn đặt phòng 'Da_Coc' trong ngày {TARGET_DATE_STR}...", CYAN)
        cursor.execute(f"""
            SELECT COUNT(*) AS Total 
            FROM DatPhong 
            WHERE NgayCheckIn <= '{TARGET_DATE_STR}' AND NgayCheckOut >= '{TARGET_DATE_STR}' AND TrangThaiDon = 'Da_Coc'
        """)
        count1 = cursor.fetchone()['Total']
        print_step("Lễ tân (T1)", f"Kết quả lần 1 = {count1} đơn.", CYAN)
        
        event_read_1.set()  # Báo cho Khách C biết đã đọc xong lần 1
        event_insert.wait() # Chờ Khách C insert xong
        
        print_step("Lễ tân (T1)", f"Lần 2: Đếm lại tổng số đơn đặt phòng 'Da_Coc' ngày {TARGET_DATE_STR}...", CYAN)
        cursor.execute(f"""
            SELECT COUNT(*) AS Total 
            FROM DatPhong 
            WHERE NgayCheckIn <= '{TARGET_DATE_STR}' AND NgayCheckOut >= '{TARGET_DATE_STR}' AND TrangThaiDon = 'Da_Coc'
        """)
        count2 = cursor.fetchone()['Total']
        print_step("Lễ tân (T1)", f"Kết quả lần 2 = {count2} đơn.", CYAN)
        
        conn.commit()
        conn.close()
        
        if count2 > count1:
            print_step("Lễ tân (T1)", f"{RED}{BOLD}HẬU QUẢ: Xuất hiện dữ liệu BÓNG MA (Phantom Read)! Số đơn nhảy từ {count1} lên {count2}.{RESET}", CYAN)
        else:
            print_step("Lễ tân (T1)", f"{GREEN}Số liệu đồng nhất.{RESET}", CYAN)

    def customer_thread():
        event_read_1.wait() # Chờ Lễ tân đọc xong lần 1
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("START TRANSACTION")
        
        print_step("Khách C (T2)", f"Khách C đặt phòng mới thành công cho dải ngày {NEW_CHECKIN_STR} đến {NEW_CHECKOUT_STR}...", MAGENTA)
        cursor.execute(f"""
            INSERT INTO DatPhong (MaKH, MaPhong, NgayCheckIn, NgayCheckOut, TienCoc, TrangThaiDon) 
            VALUES (3, 1, '{NEW_CHECKIN_STR}', '{NEW_CHECKOUT_STR}', 200000.00, 'Da_Coc')
        """)
        conn.commit()
        print_step("Khách C (T2)", "Khách C đã COMMIT thành công đơn đặt phòng mới.", MAGENTA)
        
        conn.close()
        event_insert.set() # Báo cho Lễ tân biết đã insert và commit xong

    t1 = threading.Thread(target=receptionist_thread)
    t2 = threading.Thread(target=customer_thread)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

def run_demo_solved():
    print(f"\n{BOLD}{YELLOW}--- PHẦN 2: KHI CÓ GIẢI PHÁP PHÒNG THỦ (SERIALIZABLE + GAP LOCKS / NEXT-KEY LOCKS) ---{RESET}")
    print("Mô tả: Lễ tân dùng mức cô lập SERIALIZABLE. Khi Khách C chèn mới vào dải lịch sẽ bị MySQL BLOCK.")
    
    event_read_1 = threading.Event()
    event_receptionist_done = threading.Event()

    def receptionist_thread():
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Sử dụng SERIALIZABLE
        cursor.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
        cursor.execute("START TRANSACTION")
        
        print_step("Lễ tân (T1)", f"Lần 1: Đếm tổng số đơn đặt phòng 'Da_Coc' trong ngày {TARGET_DATE_STR}...", CYAN)
        cursor.execute(f"""
            SELECT COUNT(*) AS Total 
            FROM DatPhong 
            WHERE NgayCheckIn <= '{TARGET_DATE_STR}' AND NgayCheckOut >= '{TARGET_DATE_STR}' AND TrangThaiDon = 'Da_Coc'
        """)
        count1 = cursor.fetchone()['Total']
        print_step("Lễ tân (T1)", f"Kết quả lần 1 = {count1} đơn. (Đã thiết lập Gap Lock)", CYAN)
        
        event_read_1.set()  # Báo cho Khách C biết đã đọc xong lần 1
        
        # Để Khách C có thời gian chạy lệnh insert và bị block
        time.sleep(2)
        
        print_step("Lễ tân (T1)", f"Lần 2: Đếm lại tổng số đơn đặt phòng 'Da_Coc' ngày {TARGET_DATE_STR}...", CYAN)
        cursor.execute(f"""
            SELECT COUNT(*) AS Total 
            FROM DatPhong 
            WHERE NgayCheckIn <= '{TARGET_DATE_STR}' AND NgayCheckOut >= '{TARGET_DATE_STR}' AND TrangThaiDon = 'Da_Coc'
        """)
        count2 = cursor.fetchone()['Total']
        print_step("Lễ tân (T1)", f"Kết quả lần 2 = {count2} đơn.", CYAN)
        
        conn.commit()
        print_step("Lễ tân (T1)", "Lễ tân COMMIT giao dịch, giải phóng khóa.", CYAN)
        conn.close()
        
        event_receptionist_done.set()
        
        print_step("Lễ tân (T1)", f"{GREEN}{BOLD}KẾT QUẢ: Lễ tân luôn đọc nhất quán {count1} đơn trong suốt giao tác. Không bị Phantom Read!{RESET}", CYAN)

    def customer_thread():
        event_read_1.wait() # Chờ Lễ tân đọc xong lần 1 và khóa dải
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("START TRANSACTION")
        
        print_step("Khách C (T2)", "Cố gắng chèn đơn đặt phòng mới xen vào dải ngày lễ tân đang truy vấn...", MAGENTA)
        
        start_time = time.time()
        try:
            cursor.execute(f"""
                INSERT INTO DatPhong (MaKH, MaPhong, NgayCheckIn, NgayCheckOut, TienCoc, TrangThaiDon) 
                VALUES (3, 1, '{NEW_CHECKIN_STR}', '{NEW_CHECKOUT_STR}', 200000.00, 'Da_Coc')
            """)
            conn.commit()
            wait_time = time.time() - start_time
            print_step("Khách C (T2)", f"{GREEN}Thực thi thành công sau khi chờ {wait_time:.2f} giây! (Đã được mở khóa){RESET}", MAGENTA)
        except Exception as e:
            conn.rollback()
            print_step("Khách C (T2)", f"{RED}Lỗi khi chèn: {e}{RESET}", MAGENTA)
        finally:
            conn.close()

    t1 = threading.Thread(target=receptionist_thread)
    t2 = threading.Thread(target=customer_thread)
    t1.start()
    t2.start()
    t1.join()
    t2.join()


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

    print_header("VẤN ĐỀ 2: ĐỌC BÓNG MA (PHANTOM READ)")
    
    # Chạy kịch bản lỗi
    reset_database()
    run_demo_vulnerable()
    
    # Chạy kịch bản giải pháp
    reset_database()
    run_demo_solved()
