import unittest
import pymysql
import os
import sys

# Thêm thư mục gốc vào PYTHONPATH để có thể import config và app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import Config
from app.database import get_db_connection
from app.exceptions import HotelBookingException
from app.error_codes import get_error_message

class TestHotelBookingDatabase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Khởi tạo kết nối và thiết lập database sạch trước khi chạy toàn bộ test cases"""
        cls.conn = get_db_connection()
        if cls.conn is None:
            raise unittest.SkipTest(
                "Không thể kết nối đến MySQL. Vui lòng kiểm tra biến DB_HOST, DB_USER, DB_PASSWORD trong tệp .env và đảm bảo MySQL đang chạy."
            )
        
        # Nhập các tệp tin SQL để tái thiết lập Database mẫu
        cls.execute_sql_file('sql_scripts/01_schema_index.sql')
        cls.execute_sql_file('sql_scripts/02_trigger.sql')
        cls.execute_sql_file('sql_scripts/03_seed_data.sql')
        cls.execute_sql_file('sql_scripts/04_procedures_core.sql')

    @classmethod
    def tearDownClass(cls):
        """Đóng kết nối sau khi chạy xong"""
        if cls.conn:
            cls.conn.close()

    @classmethod
    def execute_sql_file(cls, filepath):
        """Đọc và thực thi các khối lệnh SQL từ tệp tin"""
        with open(filepath, 'r', encoding='utf-8') as f:
            sql_content = f.read()

        # Tách DELIMITER để thực thi trigger / procedures
        with cls.conn.cursor() as cursor:
            # Loại bỏ các comment và tách các câu lệnh SQL
            statements = []
            current_statement = []
            in_delimiter_block = False
            
            lines = sql_content.split('\n')
            for line in lines:
                # Loại bỏ phần comment -- trên cùng dòng
                line_no_comment = line
                if '--' in line:
                    line_no_comment = line.split('--')[0]
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
                        print(f"Error importing SQL statement in {filepath}: {e}")
            cls.conn.commit()

    def setUp(self):
        """Làm mới dữ liệu seed trước mỗi test case để tránh ảnh hưởng chéo"""
        self.execute_sql_file('sql_scripts/03_seed_data.sql')
        # Lấy một kết nối mới sạch cho mỗi test
        self.conn = get_db_connection()

    def tearDown(self):
        if self.conn:
            self.conn.close()

    # ====================================================================
    # 1. TEST GIAO TÁC: sp_KiemTraPhongTrong
    # ====================================================================
    def test_01_check_available_rooms_success(self):
        """Test tìm phòng trống thành công trong khoảng ngày không trùng lịch"""
        with self.conn.cursor() as cursor:
            # Tìm phòng trống từ ngày hôm nay + 10 đến ngày hôm nay + 12 (Không trùng lịch mẫu)
            cursor.callproc('sp_KiemTraPhongTrong', ('2026-07-10', '2026-07-12'))
            rooms = cursor.fetchall()
            
            # Phải trả về ít nhất các phòng đang trống: 101, 102, 201
            room_names = [r['TenPhong'] for r in rooms]
            self.assertIn('101', room_names)
            self.assertIn('102', room_names)
            self.assertIn('201', room_names)

    def test_02_check_available_rooms_overlap(self):
        """Test phòng bị loại trừ khi bị trùng lịch đặt trước đó (Overlap)"""
        with self.conn.cursor() as cursor:
            # Tìm phòng trống từ ngày hôm nay + 1 đến hôm nay + 3 (Trùng lịch phòng 201 ở Seed Data: hôm nay + 2 -> hôm nay + 5)
            # Lưu ý: Phòng 201 ở seed data có MaPhong = 3
            import datetime
            d_in = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
            d_out = (datetime.date.today() + datetime.timedelta(days=3)).isoformat()
            
            cursor.callproc('sp_KiemTraPhongTrong', (d_in, d_out))
            rooms = cursor.fetchall()
            
            # Phòng 201 (MaPhong=3) phải bị ẩn đi do xung đột lịch đặt 'Da_Coc' mặc dù trạng thái vật lý bảng Phong đang ghi là 'Trong'
            room_names = [r['TenPhong'] for r in rooms]
            self.assertNotIn('201', room_names)

    # ====================================================================
    # 2. TEST GIAO TÁC: sp_TaoDatPhong (Overbooking & Serializability)
    # ====================================================================
    def test_03_create_booking_success(self):
        """Test đặt phòng thành công với đầy đủ thông tin hợp lệ"""
        with self.conn.cursor() as cursor:
            # Đặt phòng 101 (MaPhong=1) từ hôm nay + 10 đến hôm nay + 12
            cursor.callproc('sp_TaoDatPhong', (1, 1, '2026-07-10', '2026-07-12', 200000.00))
            self.conn.commit()
            
            # Kiểm tra xem đơn đặt phòng đã được ghi xuống DB chưa
            cursor.execute("SELECT * FROM DatPhong WHERE MaPhong = 1 AND NgayCheckIn = '2026-07-10'")
            booking = cursor.fetchone()
            self.assertIsNotNone(booking)
            self.assertEqual(booking['TrangThaiDon'], 'Da_Coc')

    def test_04_create_booking_fail_overbooking(self):
        """Test đặt phòng thất bại (Overbooking) ném mã lỗi 52001"""
        import datetime
        d_in = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        d_out = (datetime.date.today() + datetime.timedelta(days=3)).isoformat()
        
        with self.conn.cursor() as cursor:
            # Phòng 201 (MaPhong=3) đã bị đặt từ hôm nay + 2 đến hôm nay + 5.
            # Tiến hành đặt trùng thời gian sẽ bị SIGNAL ném lỗi 52001
            with self.assertRaises(pymysql.MySQLError) as context:
                cursor.callproc('sp_TaoDatPhong', (1, 3, d_in, d_out, 200000.00))
            
            # Kiểm tra mã lỗi trả về
            errno = context.exception.args[0]
            if isinstance(errno, int) and errno < 0:
                errno = 65536 + errno
            self.assertEqual(errno, 52001)

    def test_05_create_booking_fail_maintenance(self):
        """Test đặt phòng thất bại do phòng đang bảo trì ném mã lỗi 52003"""
        with self.conn.cursor() as cursor:
            # Phòng 302 (MaPhong=6) đang có trạng thái 'Bao_Tri' trong database
            with self.assertRaises(pymysql.MySQLError) as context:
                cursor.callproc('sp_TaoDatPhong', (1, 6, '2026-07-10', '2026-07-12', 200000.00))
            
            errno = context.exception.args[0]
            if isinstance(errno, int) and errno < 0:
                errno = 65536 + errno
            self.assertEqual(errno, 52003)

    # ====================================================================
    # 3. TEST GIAO TÁC: sp_XuLyCheckIn (Nhận phòng)
    # ====================================================================
    def test_06_checkin_success(self):
        """Test nhận phòng thành công (Đổi trạng thái đơn & trạng thái phòng)"""
        with self.conn.cursor() as cursor:
            # Lấy đơn đặt phòng số 1 (Đang ở trạng thái 'Da_Coc', MaPhong = 3)
            cursor.callproc('sp_XuLyCheckIn', (1,))
            self.conn.commit()
            
            # Kiểm tra đơn đặt phòng đổi sang 'Da_Nhan_Phong'
            cursor.execute("SELECT TrangThaiDon FROM DatPhong WHERE MaDatPhong = 1")
            dp = cursor.fetchone()
            self.assertEqual(dp['TrangThaiDon'], 'Da_Nhan_Phong')
            
            # Kiểm tra phòng 201 (MaPhong=3) đổi trạng thái vật lý sang 'Dang_O'
            cursor.execute("SELECT TrangThai FROM Phong WHERE MaPhong = 3")
            phong = cursor.fetchone()
            self.assertEqual(phong['TrangThai'], 'Dang_O')

    # ====================================================================
    # 4. TEST GIAO TÁC: sp_XuLyCheckOut & TRIGGER
    # ====================================================================
    def test_07_checkout_and_trigger_success(self):
        """Test trả phòng thành công: tính tiền (fn_TinhTienPhong) + tạo hóa đơn + kích hoạt Trigger dọn dẹp"""
        with self.conn.cursor() as cursor:
            # Cần chuyển đơn 1 sang 'Da_Nhan_Phong' trước để mô phỏng khách đang ở
            cursor.execute("UPDATE DatPhong SET TrangThaiDon = 'Da_Nhan_Phong' WHERE MaDatPhong = 1")
            cursor.execute("UPDATE Phong SET TrangThai = 'Dang_O' WHERE MaPhong = 3")
            self.conn.commit()
            
            # Thực hiện checkout đơn 1, tiền dịch vụ phát sinh = 150.000 VNĐ
            cursor.callproc('sp_XuLyCheckOut', (1, 150000.00))
            self.conn.commit()
            
            # 1. Kiểm tra đơn đặt phòng chuyển sang 'Hoan_Thanh'
            cursor.execute("SELECT TrangThaiDon FROM DatPhong WHERE MaDatPhong = 1")
            dp = cursor.fetchone()
            self.assertEqual(dp['TrangThaiDon'], 'Hoan_Thanh')
            
            # 2. Kiểm tra hóa đơn tài chính đã được tạo thành công
            cursor.execute("SELECT * FROM HoaDon WHERE MaDatPhong = 1")
            invoice = cursor.fetchone()
            self.assertIsNotNone(invoice)
            
            # Giá phòng 201 (Deluxe) = 1.400.000 VNĐ/đêm. Lưu trú 3 đêm (hôm nay+2 -> hôm nay+5) = 4.200.000 VNĐ
            # Tổng tiền = 4.200.000 + 150.000 = 4.350.000 VNĐ
            self.assertEqual(float(invoice['TienPhong']), 4200000.00)
            self.assertEqual(float(invoice['TongTien']), 4350000.00)
            
            # 3. KIỂM TRA TRIGGER: Trạng thái phòng 201 (MaPhong=3) tự động chuyển sang 'Dang_Don_Dep'
            cursor.execute("SELECT TrangThai FROM Phong WHERE MaPhong = 3")
            phong = cursor.fetchone()
            self.assertEqual(phong['TrangThai'], 'Dang_Don_Dep')

    # ====================================================================
    # 5. TEST GIAO TÁC: sp_HuyDatPhong (Phạt cọc hủy muộn)
    # ====================================================================
    def test_08_cancel_booking_early_refund(self):
        """Test hủy đơn sớm (trên 3 ngày): hoàn cọc 100%"""
        with self.conn.cursor() as cursor:
            # Tạo 1 đơn mới nhận phòng sau 5 ngày
            import datetime
            future_checkin = (datetime.date.today() + datetime.timedelta(days=5)).isoformat()
            future_checkout = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
            
            cursor.execute(
                "INSERT INTO DatPhong (MaKH, MaPhong, NgayCheckIn, NgayCheckOut, TienCoc, TrangThaiDon) VALUES (1, 1, %s, %s, 500000.00, 'Da_Coc')",
                (future_checkin, future_checkout)
            )
            booking_id = cursor.lastrowid
            self.conn.commit()
            
            # Thực thi hủy đơn
            cursor.callproc('sp_HuyDatPhong', (booking_id,))
            self.conn.commit()
            
            # Kiểm tra trạng thái và tiền cọc (Giữ nguyên 500.000)
            cursor.execute("SELECT TrangThaiDon, TienCoc FROM DatPhong WHERE MaDatPhong = %s", (booking_id,))
            dp = cursor.fetchone()
            self.assertEqual(dp['TrangThaiDon'], 'Da_Huy')
            self.assertEqual(float(dp['TienCoc']), 500000.00)

    def test_09_cancel_booking_late_penalty(self):
        """Test hủy đơn muộn (dưới 3 ngày): tịch thu cọc về 0"""
        with self.conn.cursor() as cursor:
            # Tạo đơn mới nhận phòng sau 1 ngày (hủy sát giờ)
            import datetime
            future_checkin = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
            future_checkout = (datetime.date.today() + datetime.timedelta(days=3)).isoformat()
            
            cursor.execute(
                "INSERT INTO DatPhong (MaKH, MaPhong, NgayCheckIn, NgayCheckOut, TienCoc, TrangThaiDon) VALUES (1, 1, %s, %s, 500000.00, 'Da_Coc')",
                (future_checkin, future_checkout)
            )
            booking_id = cursor.lastrowid
            self.conn.commit()
            
            # Thực thi hủy đơn
            cursor.callproc('sp_HuyDatPhong', (booking_id,))
            self.conn.commit()
            
            # Kiểm tra trạng thái và tiền cọc bị phạt về 0
            cursor.execute("SELECT TrangThaiDon, TienCoc FROM DatPhong WHERE MaDatPhong = %s", (booking_id,))
            dp = cursor.fetchone()
            self.assertEqual(dp['TrangThaiDon'], 'Da_Huy')
            self.assertEqual(float(dp['TienCoc']), 0.00)


if __name__ == '__main__':
    unittest.main()
