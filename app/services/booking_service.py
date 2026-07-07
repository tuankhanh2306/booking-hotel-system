from app.database import get_db_connection
from app.exceptions import HotelBookingException
import pymysql

# Dữ liệu phòng mẫu khi chạy ở chế độ PREVIEW (không có DB)
MOCK_PHONG = [
    {"MaPhong": 1, "TenPhong": "101", "Tang": 1, "TenLoai": "Standard", "SucChuaToiDa": 2, "GiaTieuChuan": 800000, "TrangThai": "Trong"},
    {"MaPhong": 2, "TenPhong": "102", "Tang": 1, "TenLoai": "Standard", "SucChuaToiDa": 2, "GiaTieuChuan": 850000, "TrangThai": "Trong"},
    {"MaPhong": 3, "TenPhong": "201", "Tang": 2, "TenLoai": "Deluxe", "SucChuaToiDa": 2, "GiaTieuChuan": 1400000, "TrangThai": "Trong"},
    {"MaPhong": 4, "TenPhong": "202", "Tang": 2, "TenLoai": "Deluxe", "SucChuaToiDa": 3, "GiaTieuChuan": 1600000, "TrangThai": "Dang_O"},
    {"MaPhong": 5, "TenPhong": "301", "Tang": 3, "TenLoai": "Suite", "SucChuaToiDa": 4, "GiaTieuChuan": 3000000, "TrangThai": "Dang_Don_Dep"},
    {"MaPhong": 6, "TenPhong": "302", "Tang": 3, "TenLoai": "Suite", "SucChuaToiDa": 4, "GiaTieuChuan": 3500000, "TrangThai": "Bao_Tri"},
]

def kiem_tra_phong_trong(ngay_checkin, ngay_checkout, loai=None, gia_min=None, gia_max=None):
    conn = get_db_connection()
    if conn is None:
        # Chế độ Preview
        rooms = [r for r in MOCK_PHONG if r["TrangThai"] == "Trong"]
        if loai:
            rooms = [r for r in rooms if r["TenLoai"] == loai]
        if gia_min:
            rooms = [r for r in rooms if r["GiaTieuChuan"] >= int(gia_min)]
        if gia_max:
            rooms = [r for r in rooms if r["GiaTieuChuan"] <= int(gia_max)]
        return rooms

    try:
        with conn.cursor() as cursor:
            # Gọi Stored Procedure sp_KiemTraPhongTrong
            cursor.callproc('sp_KiemTraPhongTrong', (ngay_checkin, ngay_checkout))
            rooms = cursor.fetchall()
            
            # Thực hiện lọc thêm ở Backend đối với các tiêu chí tìm kiếm phụ
            if loai:
                rooms = [r for r in rooms if r.get("TenLoai") == loai]
            if gia_min:
                rooms = [r for r in rooms if r.get("GiaTieuChuan", 0) >= int(gia_min)]
            if gia_max:
                rooms = [r for r in rooms if r.get("GiaTieuChuan", 0) <= int(gia_max)]
            return rooms
    except pymysql.MySQLError as e:
        errno = e.args[0] if e.args else 50000
        if isinstance(errno, int) and errno < 0:
            errno = 65536 + errno
        msg = e.args[1] if len(e.args) > 1 else str(e)
        raise HotelBookingException(errno, msg)
    finally:
        conn.close()

def tao_dat_phong(ma_kh, ma_phong, ngay_checkin, ngay_checkout, tien_coc):
    from datetime import datetime, date
    
    # Kiểm tra ngày đặt phòng hợp lệ (phải trước ít nhất 1 ngày)
    try:
        if isinstance(ngay_checkin, str):
            checkin_date = datetime.strptime(ngay_checkin, "%Y-%m-%d").date()
        else:
            checkin_date = ngay_checkin
            
        if checkin_date <= date.today():
            raise HotelBookingException(51004, "Chỉ được phép đặt phòng trước ít nhất 1 ngày.")
    except HotelBookingException:
        raise
    except Exception:
        pass

    from config import Config
    conn = get_db_connection()
    if conn is None:
        # Chế độ Preview giả lập đặt phòng thành công
        return True

    try:
        with conn.cursor() as cursor:
            if Config.USE_PROTECTION:
                # === AN TOÀN: SERIALIZABLE + SELECT FOR UPDATE + sleep 6s + INSERT ===
                # (Chống hoàn toàn mọi lỗi đặt trùng phòng dù có thời gian chờ chậm 6 giây nhờ cơ chế khóa SERIALIZABLE + FOR UPDATE)
                cursor.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                cursor.execute("START TRANSACTION")
                
                # 1. SELECT kiểm tra phòng trống và khóa dải ngày/phòng (FOR UPDATE)
                cursor.execute("""
                    SELECT COUNT(*) AS ConflictCount 
                    FROM DatPhong 
                    WHERE MaPhong = %s 
                      AND NgayCheckIn < %s 
                      AND NgayCheckOut > %s 
                      AND TrangThaiDon IN ('Cho_Duyet', 'Da_Coc', 'Da_Nhan_Phong')
                    FOR UPDATE
                """, (ma_phong, ngay_checkout, ngay_checkin))
                res = cursor.fetchone()
                conflict_count = res['ConflictCount'] if res else 0
                
                if conflict_count > 0:
                    raise pymysql.MySQLError(52001, "Phong khong con trong (Overbooking).")
                
                # 2. Giả lập trễ 6 giây (nhưng vì có khóa dải lịch, luồng khác chạy song song sẽ bị block chờ)
                import time
                time.sleep(6)
                
                # 3. Tiến hành chèn an toàn
                cursor.execute("""
                    INSERT INTO DatPhong (MaKH, MaPhong, NgayCheckIn, NgayCheckOut, TienCoc, TrangThaiDon)
                    VALUES (%s, %s, %s, %s, %s, 'Da_Coc')
                """, (ma_kh, ma_phong, ngay_checkin, ngay_checkout, tien_coc))
            else:
                # === GIẢ LẬP LỖI: Chèn thô trực tiếp (Vulnerable Mode) ===
                # (REPEATABLE READ mặc định, không khóa, kiểm tra phòng trống nhưng có trễ 6 giây và không dùng khóa nên gây lỗi)
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                cursor.execute("START TRANSACTION")
                
                # 1. SELECT kiểm tra phòng trống (đọc dải ngày trùng)
                cursor.execute("""
                    SELECT COUNT(*) AS ConflictCount 
                    FROM DatPhong 
                    WHERE MaPhong = %s 
                      AND NgayCheckIn < %s 
                      AND NgayCheckOut > %s 
                      AND TrangThaiDon IN ('Cho_Duyet', 'Da_Coc', 'Da_Nhan_Phong')
                """, (ma_phong, ngay_checkout, ngay_checkin))
                res = cursor.fetchone()
                conflict_count = res['ConflictCount'] if res else 0
                
                # 2. Giả lập trễ 6 giây để tạo race condition
                import time
                time.sleep(6)
                
                # 3. Tiến hành chèn thô
                cursor.execute("""
                    INSERT INTO DatPhong (MaKH, MaPhong, NgayCheckIn, NgayCheckOut, TienCoc, TrangThaiDon)
                    VALUES (%s, %s, %s, %s, %s, 'Da_Coc')
                """, (ma_kh, ma_phong, ngay_checkin, ngay_checkout, tien_coc))
            conn.commit()
            return True
    except pymysql.MySQLError as e:
        conn.rollback()
        # Đẩy lỗi về Exception Handler
        errno = e.args[0] if e.args else 50000
        if isinstance(errno, int) and errno < 0:
            errno = 65536 + errno
        msg = e.args[1] if len(e.args) > 1 else str(e)
        raise HotelBookingException(errno, msg)
    finally:
        conn.close()
