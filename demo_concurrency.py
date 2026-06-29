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
    """Làm sạch và tái lập cơ sở dữ liệu trước mỗi Demo"""
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
                    # Bỏ qua lỗi drop nếu không có
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
# DEMO 1: ĐẶT TRÙNG PHÒNG (LOST UPDATE / OVERBOOKING)
# ====================================================================
def run_demo_1_overbooking_vulnerable():
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
        
        print_step(client_name, "Bước 1: SELECT kiểm tra phòng 101 (MaPhong=1) từ 2026-07-25 đến 2026-07-28...", color)
        
        # Quét lịch đặt phòng hiện có
        query = """
            SELECT COUNT(*) AS ConflictCount 
            FROM DatPhong 
            WHERE MaPhong = 1 
              AND NgayCheckIn < '2026-07-28' 
              AND NgayCheckOut > '2026-07-25' 
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
            insert_query = """
                INSERT INTO DatPhong (MaKH, MaPhong, NgayCheckIn, NgayCheckOut, TienCoc, TrangThaiDon) 
                VALUES (%s, 1, '2026-07-25', '2026-07-28', 200000.00, 'Da_Coc')
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

def run_demo_1_overbooking_solved():
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
            cursor.callproc('sp_TaoDatPhong', (customer_id, 1, '2026-07-25', '2026-07-28', 200000.00))
            conn.commit()
            print_step(client_name, f"{GREEN}ĐẶT PHÒNG THÀNH CÔNG!{RESET}", color)
            results.append((client_name, "Thành công"))
        except pymysql.MySQLError as e:
            conn.rollback()
            errno = e.args[0]
            if isinstance(errno, int) and errno < 0:
                errno = 65536 + errno
            msg = e.args[1] if len(e.args) > 1 else str(e)
            
            # Giải mã mã lỗi hệ thống
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


# ====================================================================
# DEMO 2: ĐỌC BÓNG MA (PHANTOM READ)
# ====================================================================
def run_demo_2_phantom_vulnerable():
    print(f"\n{BOLD}{YELLOW}--- PHẦN 1: KHI CHƯA CÓ PHƯƠNG ÁN NGĂN CHẶN BÓNG MA (VULNERABLE) ---{RESET}")
    print("Mô tả: Lễ tân dùng REPEATABLE READ đếm phòng cọc. Khách hàng C chèn mới. Lễ tân đếm lại thấy tăng (Phantom Read).")
    
    event_read_1 = threading.Event()
    event_insert = threading.Event()
    event_read_2 = threading.Event()

    def receptionist_thread():
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Sử dụng READ COMMITTED để mô phỏng rõ Phantom Read (hoặc REPEATABLE READ nhưng không dùng khóa)
        cursor.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
        cursor.execute("START TRANSACTION")
        
        print_step("Lễ tân (T1)", "Lần 1: Đếm tổng số đơn đặt phòng 'Da_Coc' trong ngày 2026-06-25...", CYAN)
        cursor.execute("""
            SELECT COUNT(*) AS Total 
            FROM DatPhong 
            WHERE NgayCheckIn <= '2026-06-25' AND NgayCheckOut >= '2026-06-25' AND TrangThaiDon = 'Da_Coc'
        """)
        count1 = cursor.fetchone()['Total']
        print_step("Lễ tân (T1)", f"Kết quả lần 1 = {count1} đơn.", CYAN)
        
        event_read_1.set()  # Báo cho Khách C biết đã đọc xong lần 1
        event_insert.wait() # Chờ Khách C insert xong
        
        print_step("Lễ tân (T1)", "Lần 2: Đếm lại tổng số đơn đặt phòng 'Da_Coc' ngày 2026-06-25...", CYAN)
        cursor.execute("""
            SELECT COUNT(*) AS Total 
            FROM DatPhong 
            WHERE NgayCheckIn <= '2026-06-25' AND NgayCheckOut >= '2026-06-25' AND TrangThaiDon = 'Da_Coc'
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
        
        print_step("Khách C (T2)", "Khách C đặt phòng mới thành công cho ngày 2026-06-25...", MAGENTA)
        cursor.execute("""
            INSERT INTO DatPhong (MaKH, MaPhong, NgayCheckIn, NgayCheckOut, TienCoc, TrangThaiDon) 
            VALUES (3, 1, '2026-06-24', '2026-06-27', 200000.00, 'Da_Coc')
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

def run_demo_2_phantom_solved():
    print(f"\n{BOLD}{YELLOW}--- PHẦN 2: KHI CÓ GIẢI PHÁP PHÒNG THỦ (SERIALIZABLE + GAP LOCKS / NEXT-KEY LOCKS) ---{RESET}")
    print("Mô tả: Lễ tân dùng mức cô lập SERIALIZABLE. Khi Khách C chèn mới vào dải lịch sẽ bị MySQL BLOCK.")
    
    event_read_1 = threading.Event()
    event_insert_started = threading.Event()
    event_receptionist_done = threading.Event()

    def receptionist_thread():
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Sử dụng SERIALIZABLE
        cursor.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
        cursor.execute("START TRANSACTION")
        
        print_step("Lễ tân (T1)", "Lần 1: Đếm tổng số đơn đặt phòng 'Da_Coc' trong ngày 2026-06-25...", CYAN)
        # Sử dụng SELECT có khóa Next-key / Gap lock trên chỉ mục
        cursor.execute("""
            SELECT COUNT(*) AS Total 
            FROM DatPhong 
            WHERE NgayCheckIn <= '2026-06-25' AND NgayCheckOut >= '2026-06-25' AND TrangThaiDon = 'Da_Coc'
        """)
        count1 = cursor.fetchone()['Total']
        print_step("Lễ tân (T1)", f"Kết quả lần 1 = {count1} đơn. (Đã thiết lập Gap Lock)", CYAN)
        
        event_read_1.set()  # Báo cho Khách C biết đã đọc xong lần 1
        
        # Để Khách C có thời gian chạy lệnh insert và bị block
        time.sleep(2)
        
        print_step("Lễ tân (T1)", "Lần 2: Đếm lại tổng số đơn đặt phòng 'Da_Coc' ngày 2026-06-25...", CYAN)
        cursor.execute("""
            SELECT COUNT(*) AS Total 
            FROM DatPhong 
            WHERE NgayCheckIn <= '2026-06-25' AND NgayCheckOut >= '2026-06-25' AND TrangThaiDon = 'Da_Coc'
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
            cursor.execute("""
                INSERT INTO DatPhong (MaKH, MaPhong, NgayCheckIn, NgayCheckOut, TienCoc, TrangThaiDon) 
                VALUES (3, 1, '2026-06-24', '2026-06-27', 200000.00, 'Da_Coc')
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


# ====================================================================
# DEMO 3: KHÓA CHẾT (DEADLOCK)
# ====================================================================
def run_demo_3_deadlock():
    print(f"\n{BOLD}{YELLOW}--- PHẦN 1: MÔ PHỎNG HIỆN TƯỢNG DEADLOCK ---{RESET}")
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


# ====================================================================
# DEMO 4: SAI LỆCH DOANH THU (DIRTY READ / UNREPEATABLE READ)
# ====================================================================
def run_demo_4_dirty_read_vulnerable():
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

def run_demo_4_dirty_read_solved():
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

    t1 = threading.Thread(target=receptionist_thread)
    t2 = threading.Thread(target=manager_thread)
    t1.start()
    t2.start()
    t1.join()
    t2.join()


if __name__ == '__main__':
    # Bật cờ cho phép in mã ANSI màu sắc trên Windows CMD/Powershell
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
        # Nếu lỗi là do chưa có database (mã lỗi 1049)
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
            print(f"\n\033[93m\033[1mGợi ý khắc phục:\033[0m")
            print(" 1. Hãy kiểm tra xem dịch vụ MySQL đã được bật chưa (XAMPP, WampServer, Docker, Windows Service...).")
            print(" 2. Kiểm tra lại cổng (DB_PORT) trong file .env (cổng mặc định là 3306, nhưng một số máy có thể chạy 3307).")
            print(" 3. Đảm bảo bạn đã tạo Database tên là \033[96m'hotel_booking_db'\033[0m.")
            print("    (Chạy câu lệnh: CREATE DATABASE IF NOT EXISTS hotel_booking_db;)")
            print(" 4. Kiểm tra lại tên đăng nhập (DB_USER) và mật khẩu (DB_PASSWORD) trong file .env.")
            print()
            sys.exit(1)

    print(f"\n{BOLD}{CYAN}=== CHƯƠNG TRÌNH DEMO CHI TIẾT 4 VẤN ĐỀ ĐỒNG THỜI (CONCURRENCY ISSUES) ==={RESET}")
    
    # ----------------------------------------------------
    # DEMO 1
    # ----------------------------------------------------
    print_header("VẤN ĐỀ 1: ĐẶT TRÙNG PHÒNG (LOST UPDATE / OVERBOOKING)")
    reset_database()
    run_demo_1_overbooking_vulnerable()
    
    reset_database()
    run_demo_1_overbooking_solved()

    # ----------------------------------------------------
    # DEMO 2
    # ----------------------------------------------------
    print_header("VẤN ĐỀ 2: ĐỌC BÓNG MA (PHANTOM READ)")
    reset_database()
    run_demo_2_phantom_vulnerable()
    
    reset_database()
    run_demo_2_phantom_solved()

    # ----------------------------------------------------
    # DEMO 3
    # ----------------------------------------------------
    print_header("VẤN ĐỀ 3: KHÓA CHẾT (DEADLOCK)")
    reset_database()
    run_demo_3_deadlock()

    # ----------------------------------------------------
    # DEMO 4
    # ----------------------------------------------------
    print_header("VẤN ĐỀ 4: SAI LỆCH DOANH THU (DIRTY READ)")
    reset_database()
    run_demo_4_dirty_read_vulnerable()
    
    reset_database()
    run_demo_4_dirty_read_solved()

    print(f"\n{BOLD}{GREEN}=== ĐÃ HOÀN THÀNH TẤT CẢ CÁC KỊCH BẢN DEMO ==={RESET}\n")
