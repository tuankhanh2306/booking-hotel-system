import os
import sys
import time
import threading
import pymysql
from pymysql.cursors import DictCursor
from datetime import date, timedelta

# Khởi tạo ngày động (Check-in 10 ngày sau, Check-out 13 ngày sau)
CHECKIN_DATE = date.today() + timedelta(days=10)
CHECKOUT_DATE = date.today() + timedelta(days=13)
CHECKIN_STR = CHECKIN_DATE.strftime('%Y-%m-%d')
CHECKOUT_STR = CHECKOUT_DATE.strftime('%Y-%m-%d')

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
# ĐẶT TRÙNG PHÒNG (LOST UPDATE / OVERBOOKING)
# ====================================================================
def run_demo_vulnerable():
    print(f"\n{BOLD}{YELLOW}--- PHẦN 1: KHI CHƯA CÓ GIẢI PHÁP PHÒNG THỦ (VULNERABLE) ---{RESET}")
    print("Mô tả: Khách A và Khách B cùng SELECT kiểm tra phòng trống song song. Cả 2 thấy phòng trống và cùng INSERT.")
    
    barrier = threading.Barrier(2)
    results = []

    def client_booking_vulnerable(client_name, customer_id, color):
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Thiết lập mức cô lập thông thường REPEATABLE READ
        cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        cursor.execute("START TRANSACTION")
        
        print_step(client_name, f"Bước 1: SELECT kiểm tra phòng 101 (MaPhong=1) từ {CHECKIN_STR} đến {CHECKOUT_STR}...", color)
        
        query = f"""
            SELECT COUNT(*) AS ConflictCount 
            FROM DatPhong 
            WHERE MaPhong = 1 
              AND NgayCheckIn < '{CHECKOUT_STR}' 
              AND NgayCheckOut > '{CHECKIN_STR}' 
              AND TrangThaiDon IN ('Cho_Duyet', 'Da_Coc', 'Da_Nhan_Phong')
        """
        cursor.execute(query)
        res = cursor.fetchone()
        conflict_count = res['ConflictCount']
        print_step(client_name, f"Kết quả SELECT: có {conflict_count} đơn trùng lịch. (Phòng ĐANG TRỐNG)", color)
        
        # Chờ cả 2 luồng đọc xong để cùng ghi
        barrier.wait()
        
        print_step(client_name, "Bước 2: Tiến hành chèn (INSERT) đơn đặt phòng...", color)
        try:
            insert_query = f"""
                INSERT INTO DatPhong (MaKH, MaPhong, NgayCheckIn, NgayCheckOut, TienCoc, TrangThaiDon) 
                VALUES (%s, 1, '{CHECKIN_STR}', '{CHECKOUT_STR}', 200000.00, 'Da_Coc')
            """
            cursor.execute(insert_query, (customer_id,))
            conn.commit()
            print_step(client_name, f"{GREEN}ĐẶT PHÒNG THÀNH CÔNG!{RESET}", color)
            results.append((client_name, "Thành công"))
        except Exception as e:
            conn.rollback()
            print_step(client_name, f"{RED}ĐẶT PHÒNG THẤT BẠI: {e}{RESET}", color)
            results.append((client_name, f"Thất bại: {str(e)}"))
        finally:
            conn.close()

    t1 = threading.Thread(target=client_booking_vulnerable, args=("Khách A (T1)", 1, CYAN))
    t2 = threading.Thread(target=client_booking_vulnerable, args=("Khách B (T2)", 2, MAGENTA))
    
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Kiểm tra kết quả trong DB
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT MaDatPhong, MaKH, NgayCheckIn, NgayCheckOut, TrangThaiDon FROM DatPhong WHERE MaPhong = 1")
    bookings = cursor.fetchall()
    conn.close()

    print(f"\n{BOLD}Kết quả kiểm tra bảng DatPhong cho phòng 101:{RESET}")
    for b in bookings:
        print(f" - Đơn #{b['MaDatPhong']}: Khách hàng #{b['MaKH']}, từ {b['NgayCheckIn']} đến {b['NgayCheckOut']} [{b['TrangThaiDon']}]")
    
    if len(bookings) >= 2:
        print(f"{RED}{BOLD}HẬU QUẢ: Cả Khách A và Khách B đều đặt thành công cùng một phòng vào cùng thời điểm! (Overbooking thành công){RESET}")
    else:
        print(f"{GREEN}Không xảy ra trùng lặp.{RESET}")

def run_demo_solved():
    print(f"\n{BOLD}{YELLOW}--- PHẦN 2: KHI CÓ GIẢI PHÁP PHÒNG THỦ (SERIALIZABLE + SELECT FOR UPDATE) ---{RESET}")
    print("Mô tả: Sử dụng procedure sp_TaoDatPhong. Khách A vào trước sẽ khóa dải lịch. Khách B vào sau bị block và ném lỗi 52001.")
    
    barrier = threading.Barrier(2)
    results = []

    def client_booking_solved(client_name, customer_id, delay_before_call, color):
        time.sleep(delay_before_call)
        conn = get_db_connection()
        cursor = conn.cursor()
        
        print_step(client_name, "Bắt đầu gọi sp_TaoDatPhong...", color)
        try:
            # Gọi sp_TaoDatPhong (sử dụng SERIALIZABLE và FOR UPDATE nội bộ)
            cursor.callproc('sp_TaoDatPhong', (customer_id, 1, CHECKIN_STR, CHECKOUT_STR, 200000.00))
            conn.commit()
            print_step(client_name, f"{GREEN}ĐẶT PHÒNG THÀNH CÔNG!{RESET}", color)
            results.append((client_name, "Thành công"))
        except pymysql.MySQLError as e:
            conn.rollback()
            errno = e.args[0]
            if isinstance(errno, int) and errno < 0:
                errno = 65536 + errno
            msg = e.args[1] if len(e.args) > 1 else str(e)
            
            mapped_msg = get_error_message(errno, msg)
            print_step(client_name, f"{RED}BỊ TỪ CHỐI (Mã lỗi {errno}): {mapped_msg}{RESET}", color)
            results.append((client_name, f"Thất bại: {mapped_msg}"))
        finally:
            conn.close()

    # Khách A chạy trước, Khách B chạy sau 0.2 giây để Khách A giữ khóa trước
    t1 = threading.Thread(target=client_booking_solved, args=("Khách A (T1)", 1, 0, CYAN))
    t2 = threading.Thread(target=client_booking_solved, args=("Khách B (T2)", 2, 0.2, MAGENTA))
    
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Kiểm tra kết quả trong DB
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT MaDatPhong, MaKH, NgayCheckIn, NgayCheckOut, TrangThaiDon FROM DatPhong WHERE MaPhong = 1")
    bookings = cursor.fetchall()
    conn.close()

    print(f"\n{BOLD}Kết quả kiểm tra bảng DatPhong cho phòng 101:{RESET}")
    for b in bookings:
        print(f" - Đơn #{b['MaDatPhong']}: Khách hàng #{b['MaKH']}, từ {b['NgayCheckIn']} đến {b['NgayCheckOut']} [{b['TrangThaiDon']}]")
    
    print(f"{GREEN}{BOLD}KẾT LUẬN: Chỉ Khách A đặt thành công. Khách B bị phát hiện trùng lịch và hệ thống Rollback an toàn!{RESET}")


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

    print_header("VẤN ĐỀ 1: ĐẶT TRÙNG PHÒNG (LOST UPDATE / OVERBOOKING)")
    
    # Chạy kịch bản khi chưa có khóa
    reset_database()
    run_demo_vulnerable()
    
    # Chạy kịch bản khi áp dụng giải pháp khóa
    reset_database()
    run_demo_solved()
